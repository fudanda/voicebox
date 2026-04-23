"""Transcription endpoints."""

import asyncio
import re
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from .. import config, models
from ..backends import WHISPER_HF_REPOS
from ..database import Generation as DBGeneration, ProfileSample as DBProfileSample, get_db
from ..services import punctuation, transcribe
from ..services.task_queue import create_background_task
from ..utils.progress import get_progress_manager
from ..utils.tasks import get_task_manager

router = APIRouter()

UPLOAD_CHUNK_SIZE = 1024 * 1024  # 1MB
_CJK_CHAR_RE = re.compile(r"[\u3400-\u9fff\u3040-\u30ff\uac00-\ud7af]")
_PUNCTUATION_RE = re.compile(r"[\u3001\u3002\uff0c\uff01\uff1f\uff1b\uff1a,.!?;:]")


async def _write_upload_to_temp_file(file: UploadFile) -> Path:
    """Persist an uploaded audio file to a temporary path."""
    file_suffix = Path(file.filename or "").suffix or ".wav"
    with tempfile.NamedTemporaryFile(suffix=file_suffix, delete=False) as tmp:
        while chunk := await file.read(UPLOAD_CHUNK_SIZE):
            tmp.write(chunk)
        return Path(tmp.name)


async def _get_audio_duration(audio_path: Path) -> float:
    """Decode audio and return duration in seconds."""
    from ..utils.audio import load_audio

    audio, sr = await asyncio.to_thread(load_audio, str(audio_path))
    if sr == 0:
        return 0.0
    return len(audio) / sr


def _get_whisper_model_and_size(requested_model: str | None):
    """Validate whisper model size and return backend instance + resolved size."""
    whisper_model = transcribe.get_whisper_model()
    model_size = requested_model if requested_model else whisper_model.model_size

    valid_sizes = list(WHISPER_HF_REPOS.keys())
    if model_size not in valid_sizes:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid model size '{model_size}'. Must be one of: {', '.join(valid_sizes)}",
        )

    return whisper_model, model_size


async def _ensure_whisper_model_ready(whisper_model, model_size: str) -> None:
    """Ensure model is loaded or trigger download task + 202 response."""
    already_loaded = whisper_model.is_loaded() and whisper_model.model_size == model_size
    if already_loaded or whisper_model._is_model_cached(model_size):
        return

    progress_model_name = f"whisper-{model_size}"
    task_manager = get_task_manager()

    async def download_whisper_background():
        try:
            await whisper_model.load_model_async(model_size)
            task_manager.complete_download(progress_model_name)
        except Exception as e:
            task_manager.error_download(progress_model_name, str(e))

    task_manager.start_download(progress_model_name)
    create_background_task(download_whisper_background())

    raise HTTPException(
        status_code=202,
        detail={
            "message": f"Whisper model {model_size} is being downloaded. Please wait and try again.",
            "model_name": progress_model_name,
            "downloading": True,
        },
    )


def _contains_cjk(text: str) -> bool:
    return bool(_CJK_CHAR_RE.search(text))


def _contains_punctuation(text: str) -> bool:
    return bool(_PUNCTUATION_RE.search(text))


def _should_restore_punctuation(language: str | None, text: str) -> bool:
    if not config.ENABLE_PUNCTUATION_RESTORATION:
        return False

    stripped = text.strip()
    if not stripped:
        return False

    # If punctuation already exists, skip restoration.
    if _contains_punctuation(stripped):
        return False

    normalized_language = (language or "").strip().lower()
    if normalized_language == "zh":
        return True
    if normalized_language in ("", "auto"):
        return _contains_cjk(stripped)
    return False


async def _ensure_punctuation_model_ready(punctuation_restorer) -> None:
    """Ensure punctuation model is loaded or trigger download task + 202 response."""
    already_loaded = punctuation_restorer.is_loaded()
    if already_loaded or punctuation_restorer.is_model_cached():
        return

    progress_model_name = punctuation.PUNCTUATION_MODEL_NAME
    task_manager = get_task_manager()
    progress_manager = get_progress_manager()

    async def download_punctuation_background():
        try:
            await punctuation_restorer.download_model_async()
            progress_manager.mark_complete(progress_model_name)
            task_manager.complete_download(progress_model_name)
        except Exception as e:
            progress_manager.mark_error(progress_model_name, str(e))
            task_manager.error_download(progress_model_name, str(e))

    if not task_manager.is_download_active(progress_model_name):
        task_manager.start_download(progress_model_name)
        progress_manager.update_progress(
            model_name=progress_model_name,
            current=0,
            total=0,
            filename="Connecting to ModelScope...",
            status="downloading",
        )
        create_background_task(download_punctuation_background())

    raise HTTPException(
        status_code=202,
        detail={
            "message": "Punctuation model is being downloaded. Please wait and try again.",
            "model_name": progress_model_name,
            "downloading": True,
        },
    )


async def _resolve_subtitle_source(
    file: UploadFile | None,
    sample_id: str | None,
    generation_id: str | None,
    db: Session,
) -> tuple[Path, bool]:
    """
    Resolve subtitle transcription source.

    Returns:
        (audio_path, should_cleanup)
    """
    source_count = sum(1 for value in (file is not None, bool(sample_id), bool(generation_id)) if value)
    if source_count != 1:
        raise HTTPException(
            status_code=400,
            detail="Exactly one of 'file', 'sample_id', or 'generation_id' must be provided.",
        )

    if file is not None:
        return await _write_upload_to_temp_file(file), True

    if generation_id:
        generation = db.query(DBGeneration).filter_by(id=generation_id).first()
        if not generation:
            raise HTTPException(status_code=404, detail="Generation not found")

        generation_audio_path = config.resolve_storage_path(generation.audio_path)
        if generation_audio_path is None or not generation_audio_path.exists():
            raise HTTPException(status_code=404, detail="Generation audio file not found")

        return generation_audio_path, False

    sample = db.query(DBProfileSample).filter_by(id=sample_id).first()
    if not sample:
        raise HTTPException(status_code=404, detail="Sample not found")

    sample_audio_path = config.resolve_storage_path(sample.audio_path)
    if sample_audio_path is None or not sample_audio_path.exists():
        raise HTTPException(status_code=404, detail="Sample audio file not found")

    return sample_audio_path, False


@router.post("/transcribe", response_model=models.TranscriptionResponse)
async def transcribe_audio(
    file: UploadFile = File(...),
    language: str | None = Form(None),
    model: str | None = Form(None),
):
    """Transcribe audio file to text."""
    tmp_path = await _write_upload_to_temp_file(file)

    try:
        duration = await _get_audio_duration(tmp_path)
        whisper_model, model_size = _get_whisper_model_and_size(model)
        await _ensure_whisper_model_ready(whisper_model, model_size)
        text = await whisper_model.transcribe(str(tmp_path), language, model_size)

        if _should_restore_punctuation(language, text):
            punctuation_restorer = punctuation.get_punctuation_restorer()
            await _ensure_punctuation_model_ready(punctuation_restorer)
            try:
                text = await punctuation_restorer.restore_text(text)
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Punctuation restoration failed: {e}") from e

        return models.TranscriptionResponse(
            text=text,
            duration=duration,
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    finally:
        tmp_path.unlink(missing_ok=True)


@router.post("/transcribe/subtitles", response_model=models.TranscriptionSubtitlesResponse)
async def transcribe_subtitles(
    file: UploadFile | None = File(None),
    sample_id: str | None = Form(None),
    generation_id: str | None = Form(None),
    language: str | None = Form(None),
    model: str | None = Form(None),
    db: Session = Depends(get_db),
):
    """Transcribe audio and return subtitle segments."""
    source_path, should_cleanup = await _resolve_subtitle_source(file, sample_id, generation_id, db)

    try:
        duration = await _get_audio_duration(source_path)
        whisper_model, model_size = _get_whisper_model_and_size(model)
        await _ensure_whisper_model_ready(whisper_model, model_size)

        try:
            detailed = await whisper_model.transcribe_with_segments(str(source_path), language, model_size)
        except NotImplementedError as e:
            raise HTTPException(status_code=501, detail=str(e)) from e

        text = str(detailed["text"])
        segments = [models.TranscriptionSegment(**segment) for segment in detailed["segments"]]

        detection_text = text.strip() or "".join(segment.text for segment in segments)
        text_source = text.strip() or detection_text
        text_needs_restore = _should_restore_punctuation(language, text_source)
        segment_indices_to_restore = [
            idx for idx, segment in enumerate(segments) if _should_restore_punctuation(language, segment.text)
        ]

        if text_needs_restore or segment_indices_to_restore:
            punctuation_restorer = punctuation.get_punctuation_restorer()
            await _ensure_punctuation_model_ready(punctuation_restorer)
            try:
                if text_needs_restore and text_source:
                    text = await punctuation_restorer.restore_text(text_source)

                if segment_indices_to_restore:
                    subset = [segments[idx] for idx in segment_indices_to_restore]
                    restored_segments = await punctuation_restorer.restore_segments(
                        [
                            {
                                "index": segment.index,
                                "start": segment.start,
                                "end": segment.end,
                                "text": segment.text,
                            }
                            for segment in subset
                        ]
                    )
                    for idx, restored in zip(segment_indices_to_restore, restored_segments, strict=False):
                        segments[idx] = models.TranscriptionSegment(**restored)
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Punctuation restoration failed: {e}") from e

        return models.TranscriptionSubtitlesResponse(
            text=text,
            duration=duration,
            segments=segments,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    finally:
        if should_cleanup:
            source_path.unlink(missing_ok=True)
