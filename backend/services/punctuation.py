"""FunASR punctuation restoration service for Whisper post-processing."""

import asyncio
import importlib.util
import logging
import os
import threading
from pathlib import Path
from typing import TypedDict

logger = logging.getLogger(__name__)

PUNCTUATION_MODEL_ID = "iic/punc_ct-transformer_zh-cn-common-vocab272727-pytorch"
PUNCTUATION_MODEL_REVISION = "v2.0.4"
PUNCTUATION_MODEL_NAME = "punc-ct-transformer-zh-cn"


class PunctuationSegment(TypedDict):
    """Segment payload used for punctuation restoration."""

    index: int
    start: float
    end: float
    text: str


class PunctuationServiceError(RuntimeError):
    """Base error for punctuation restoration failures."""


class PunctuationModelNotCachedError(PunctuationServiceError):
    """Raised when punctuation model is required but not cached."""


class FunASRPunctuationService:
    """Provides punctuation restoration via a lazily loaded FunASR AutoModel."""

    def __init__(self):
        self._model = None
        self._lock = threading.RLock()
        self._cached_model_dir: Path | None = None

    def is_loaded(self) -> bool:
        with self._lock:
            return self._model is not None

    @staticmethod
    def _ensure_dependencies() -> None:
        missing: list[str] = []
        if importlib.util.find_spec("funasr") is None:
            missing.append("funasr")
        if importlib.util.find_spec("modelscope") is None:
            missing.append("modelscope")
        if missing:
            raise PunctuationServiceError(
                f"Punctuation restoration dependencies are missing: {', '.join(missing)}"
            )

    def is_model_cached(self) -> bool:
        if self._cached_model_dir is not None and self._cached_model_dir.exists():
            return True

        self._ensure_dependencies()
        cached = self._resolve_model_dir(local_files_only=True)
        if cached is None:
            return False
        self._cached_model_dir = cached
        return True

    async def load_model_async(self) -> None:
        await asyncio.to_thread(self._load_model_sync)

    async def download_model_async(self) -> None:
        await asyncio.to_thread(self._download_model_sync)

    async def restore_text(self, text: str) -> str:
        stripped = text.strip()
        if not stripped:
            return stripped
        await self.load_model_async()
        return await asyncio.to_thread(self._restore_text_sync, stripped)

    async def restore_segments(self, segments: list[PunctuationSegment]) -> list[PunctuationSegment]:
        if not segments:
            return segments
        await self.load_model_async()
        return await asyncio.to_thread(self._restore_segments_sync, segments)

    def _load_model_sync(self) -> None:
        if self.is_loaded():
            return

        self._ensure_dependencies()
        model_dir = self._resolve_model_dir(local_files_only=True)
        if model_dir is None:
            raise PunctuationModelNotCachedError(
                f"Punctuation model {PUNCTUATION_MODEL_ID} is not cached yet."
            )
        self._cached_model_dir = model_dir
        self._instantiate_model(model_dir)

    def _download_model_sync(self) -> None:
        self._ensure_dependencies()
        model_dir = self._resolve_model_dir(local_files_only=False)
        if model_dir is None:
            raise PunctuationServiceError(
                f"Failed to download punctuation model {PUNCTUATION_MODEL_ID}."
            )
        self._cached_model_dir = model_dir
        self._instantiate_model(model_dir)

    def _instantiate_model(self, model_dir: Path) -> None:
        with self._lock:
            if self._model is not None:
                return

            from funasr import AutoModel

            errors: list[str] = []
            candidates = [
                {"model": str(model_dir)},
                {
                    "model": PUNCTUATION_MODEL_ID,
                    "model_revision": PUNCTUATION_MODEL_REVISION,
                    "model_hub": "ms",
                },
            ]

            for kwargs in candidates:
                try:
                    self._model = AutoModel(**kwargs)
                    logger.info("Punctuation model loaded from %s", kwargs["model"])
                    return
                except Exception as exc:
                    errors.append(f"{kwargs}: {exc}")

            raise PunctuationServiceError(
                "Failed to initialize FunASR punctuation model. " + " | ".join(errors)
            )

    def _resolve_model_dir(self, *, local_files_only: bool) -> Path | None:
        from modelscope.hub.snapshot_download import snapshot_download

        calls = [
            {
                "model_id": PUNCTUATION_MODEL_ID,
                "revision": PUNCTUATION_MODEL_REVISION,
                "local_files_only": local_files_only,
            },
            {
                "model_id": PUNCTUATION_MODEL_ID,
                "model_revision": PUNCTUATION_MODEL_REVISION,
                "local_files_only": local_files_only,
            },
            {
                "model_id": PUNCTUATION_MODEL_ID,
                "local_files_only": local_files_only,
            },
            {
                "model": PUNCTUATION_MODEL_ID,
                "local_files_only": local_files_only,
            },
        ]

        for kwargs in calls:
            try:
                model_path = snapshot_download(**kwargs)
            except TypeError:
                continue
            except Exception as exc:
                if local_files_only:
                    logger.debug(
                        "ModelScope local-files-only probe failed for %s: %s",
                        kwargs,
                        exc,
                    )
                    continue
                raise PunctuationServiceError(
                    f"Failed to download punctuation model from ModelScope: {exc}"
                ) from exc

            resolved = Path(model_path)
            if resolved.exists():
                return resolved

        if local_files_only:
            return self._find_modelscope_cache_fallback()
        return None

    @staticmethod
    def _find_modelscope_cache_fallback() -> Path | None:
        cache_root = Path(os.environ.get("MODELSCOPE_CACHE", Path.home() / ".cache" / "modelscope" / "hub"))
        model_tail = Path(*PUNCTUATION_MODEL_ID.split("/"))
        candidates = [
            cache_root / "models" / model_tail,
            cache_root / model_tail,
        ]
        for candidate in candidates:
            if candidate.exists() and any(candidate.rglob("*")):
                return candidate
        return None

    def _restore_text_sync(self, text: str) -> str:
        with self._lock:
            if self._model is None:
                raise PunctuationServiceError("Punctuation model is not loaded.")
            try:
                result = self._model.generate(input=text)
            except Exception as exc:
                raise PunctuationServiceError(f"FunASR punctuation inference failed: {exc}") from exc

        restored = self._extract_text(result).strip()
        if not restored:
            raise PunctuationServiceError("FunASR punctuation returned empty text.")
        return restored

    def _restore_segments_sync(self, segments: list[PunctuationSegment]) -> list[PunctuationSegment]:
        restored: list[PunctuationSegment] = []
        for segment in segments:
            restored.append(
                {
                    "index": int(segment["index"]),
                    "start": float(segment["start"]),
                    "end": float(segment["end"]),
                    "text": self._restore_text_sync(str(segment["text"])),
                }
            )
        return restored

    @staticmethod
    def _extract_text(result: object) -> str:
        if isinstance(result, str):
            return result

        if isinstance(result, dict):
            if isinstance(result.get("text"), str):
                return result["text"]
            value = result.get("value")
            if isinstance(value, str):
                return value

        if isinstance(result, list):
            chunks: list[str] = []
            for item in result:
                text = FunASRPunctuationService._extract_text(item)
                if text:
                    chunks.append(text)
            return "".join(chunks).strip()

        if hasattr(result, "text"):
            text_attr = result.text
            if isinstance(text_attr, str):
                return text_attr

        return str(result)


_punctuation_service: FunASRPunctuationService | None = None
_punctuation_service_lock = threading.Lock()


def get_punctuation_restorer() -> FunASRPunctuationService:
    """Return process-wide punctuation restorer singleton."""
    global _punctuation_service

    if _punctuation_service is not None:
        return _punctuation_service

    with _punctuation_service_lock:
        if _punctuation_service is None:
            _punctuation_service = FunASRPunctuationService()
    return _punctuation_service
