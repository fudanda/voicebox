"""Tests for transcription endpoints with subtitle and punctuation behavior."""

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend import config
from backend.database.models import (
    Base,
    Generation as DBGeneration,
    ProfileSample as DBProfileSample,
    VoiceProfile as DBVoiceProfile,
)
from backend.routes import transcription


@pytest.fixture(autouse=True)
def _enable_punctuation_default(monkeypatch):
    monkeypatch.setattr(config, "ENABLE_PUNCTUATION_RESTORATION", True)


class DummyWhisperBackend:
    """Minimal STT backend stub for transcription route tests."""

    def __init__(
        self,
        *,
        cached: bool = True,
        model_size: str = "base",
        plain_text: str = "plain text",
        detailed_text: str = "hello world",
        detailed_segments: list[dict] | None = None,
    ):
        self._cached = cached
        self.model_size = model_size
        self._loaded = False
        self._plain_text = plain_text
        self._detailed_text = detailed_text
        self._detailed_segments = detailed_segments or [
            {"index": 0, "start": 0.0, "end": 1.2, "text": "hello"},
            {"index": 1, "start": 1.2, "end": 2.0, "text": "world"},
        ]
        self.transcribe_called = False
        self.transcribe_with_segments_called = False

    def is_loaded(self) -> bool:
        return self._loaded

    def _is_model_cached(self, _model_size: str) -> bool:
        return self._cached

    async def load_model_async(self, model_size: str) -> None:
        self._loaded = True
        self.model_size = model_size

    async def transcribe(self, _audio_path: str, _language: str | None, _model_size: str | None) -> str:
        self.transcribe_called = True
        return self._plain_text

    async def transcribe_with_segments(
        self,
        _audio_path: str,
        _language: str | None,
        _model_size: str | None,
    ):
        self.transcribe_with_segments_called = True
        return {
            "text": self._detailed_text,
            "segments": self._detailed_segments,
        }


class DummyPunctuationBackend:
    """Punctuation restorer test double."""

    def __init__(self, *, cached: bool = True, fail: bool = False):
        self._cached = cached
        self._loaded = cached
        self._fail = fail
        self.restore_text_called = False
        self.restore_segments_called = False

    def is_loaded(self) -> bool:
        return self._loaded

    def is_model_cached(self) -> bool:
        return self._cached

    async def download_model_async(self) -> None:
        self._cached = True
        self._loaded = True

    async def restore_text(self, text: str) -> str:
        self.restore_text_called = True
        if self._fail:
            raise RuntimeError("punctuation failed")
        return f"{text}。"

    async def restore_segments(self, segments: list[dict]) -> list[dict]:
        self.restore_segments_called = True
        if self._fail:
            raise RuntimeError("punctuation failed")
        return [{**segment, "text": f"{segment['text']}。"} for segment in segments]


def _build_test_client(db_session) -> TestClient:
    app = FastAPI()
    app.include_router(transcription.router)

    def _override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[transcription.get_db] = _override_get_db
    return TestClient(app)


def _create_db(tmp_path: Path):
    db_path = tmp_path / "test.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    session_local = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    return engine, session_local


def _ensure_profile(db_session, *, profile_id: str = "profile-1") -> DBVoiceProfile:
    profile = db_session.query(DBVoiceProfile).filter_by(id=profile_id).first()
    if profile:
        return profile

    profile = DBVoiceProfile(
        id=profile_id,
        name="Profile One",
        language="en",
    )
    db_session.add(profile)
    db_session.commit()
    return profile


def _seed_sample(db_session, *, sample_id: str, audio_path: str) -> None:
    profile = _ensure_profile(db_session)
    sample = DBProfileSample(
        id=sample_id,
        profile_id=profile.id,
        audio_path=audio_path,
        reference_text="sample text",
    )
    db_session.add(sample)
    db_session.commit()


def _seed_generation(db_session, *, generation_id: str, audio_path: str, status: str = "completed") -> None:
    profile = _ensure_profile(db_session)
    generation = DBGeneration(
        id=generation_id,
        profile_id=profile.id,
        text="generated text",
        language="en",
        audio_path=audio_path,
        duration=1.0,
        status=status,
    )
    db_session.add(generation)
    db_session.commit()


def _patch_audio_decode(monkeypatch, duration_seconds: float = 1.0) -> None:
    sample_count = int(16000 * duration_seconds)
    monkeypatch.setattr("backend.utils.audio.load_audio", lambda *_args, **_kwargs: ([0.0] * sample_count, 16000))


def _post_transcribe(client: TestClient, *, language: str | None = None):
    data = {}
    if language is not None:
        data["language"] = language
    return client.post(
        "/transcribe",
        data=data,
        files={"file": ("audio.wav", b"dummy", "audio/wav")},
    )


def _post_subtitles(
    client: TestClient,
    *,
    sample_id: str | None = None,
    generation_id: str | None = None,
    language: str | None = None,
):
    data = {}
    if sample_id is not None:
        data["sample_id"] = sample_id
    if generation_id is not None:
        data["generation_id"] = generation_id
    if language is not None:
        data["language"] = language
    return client.post("/transcribe/subtitles", data=data)


def test_subtitles_requires_exactly_one_source(monkeypatch, tmp_path):
    """file/sample_id/generation_id must follow exactly-one-source rule."""
    engine, session_local = _create_db(tmp_path)
    db = session_local()
    client = _build_test_client(db)

    whisper = DummyWhisperBackend(cached=True)
    monkeypatch.setattr(transcription.transcribe, "get_whisper_model", lambda: whisper)
    _patch_audio_decode(monkeypatch, 1.0)

    resp_none = client.post("/transcribe/subtitles", data={})
    assert resp_none.status_code == 400
    assert "Exactly one" in resp_none.json()["detail"]

    resp_both = client.post(
        "/transcribe/subtitles",
        data={"sample_id": "sample-1"},
        files={"file": ("audio.wav", b"dummy", "audio/wav")},
    )
    assert resp_both.status_code == 400
    assert "Exactly one" in resp_both.json()["detail"]

    resp_two_ids = client.post(
        "/transcribe/subtitles",
        data={"sample_id": "sample-1", "generation_id": "gen-1"},
    )
    assert resp_two_ids.status_code == 400
    assert "Exactly one" in resp_two_ids.json()["detail"]

    resp_three = client.post(
        "/transcribe/subtitles",
        data={"sample_id": "sample-1", "generation_id": "gen-1"},
        files={"file": ("audio.wav", b"dummy", "audio/wav")},
    )
    assert resp_three.status_code == 400
    assert "Exactly one" in resp_three.json()["detail"]

    db.close()
    engine.dispose()


def test_subtitles_sample_not_found(monkeypatch, tmp_path):
    """sample_id should return 404 when DB record does not exist."""
    engine, session_local = _create_db(tmp_path)
    db = session_local()
    client = _build_test_client(db)

    whisper = DummyWhisperBackend(cached=True)
    monkeypatch.setattr(transcription.transcribe, "get_whisper_model", lambda: whisper)
    _patch_audio_decode(monkeypatch, 1.0)

    resp = client.post("/transcribe/subtitles", data={"sample_id": "missing"})
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Sample not found"

    db.close()
    engine.dispose()


def test_subtitles_sample_audio_missing(monkeypatch, tmp_path):
    """sample_id should return 404 when sample audio file is missing."""
    engine, session_local = _create_db(tmp_path)
    db = session_local()
    client = _build_test_client(db)

    _seed_sample(db, sample_id="sample-1", audio_path="profiles/profile-1/samples/sample-1.wav")

    whisper = DummyWhisperBackend(cached=True)
    monkeypatch.setattr(transcription.transcribe, "get_whisper_model", lambda: whisper)
    _patch_audio_decode(monkeypatch, 1.0)
    monkeypatch.setattr(config, "resolve_storage_path", lambda _path: tmp_path / "does-not-exist.wav")

    resp = client.post("/transcribe/subtitles", data={"sample_id": "sample-1"})
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Sample audio file not found"

    db.close()
    engine.dispose()


def test_subtitles_generation_not_found(monkeypatch, tmp_path):
    """generation_id should return 404 when DB record does not exist."""
    engine, session_local = _create_db(tmp_path)
    db = session_local()
    client = _build_test_client(db)

    whisper = DummyWhisperBackend(cached=True)
    monkeypatch.setattr(transcription.transcribe, "get_whisper_model", lambda: whisper)
    _patch_audio_decode(monkeypatch, 1.0)

    resp = client.post("/transcribe/subtitles", data={"generation_id": "missing"})
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Generation not found"

    db.close()
    engine.dispose()


def test_subtitles_generation_audio_missing(monkeypatch, tmp_path):
    """generation_id should return 404 when generation audio file is missing."""
    engine, session_local = _create_db(tmp_path)
    db = session_local()
    client = _build_test_client(db)

    _seed_generation(db, generation_id="gen-1", audio_path="generations/gen-1.wav")

    whisper = DummyWhisperBackend(cached=True)
    monkeypatch.setattr(transcription.transcribe, "get_whisper_model", lambda: whisper)
    _patch_audio_decode(monkeypatch, 1.0)
    monkeypatch.setattr(config, "resolve_storage_path", lambda _path: tmp_path / "missing-generation.wav")

    resp = client.post("/transcribe/subtitles", data={"generation_id": "gen-1"})
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Generation audio file not found"

    db.close()
    engine.dispose()


def test_subtitles_success_with_generation_id(monkeypatch, tmp_path):
    """generation_id path should transcribe and return text/duration/segments payload."""
    engine, session_local = _create_db(tmp_path)
    db = session_local()
    client = _build_test_client(db)

    audio_file = tmp_path / "generation.wav"
    audio_file.write_bytes(b"dummy")
    _seed_generation(db, generation_id="gen-1", audio_path="generations/gen-1.wav")

    whisper = DummyWhisperBackend(cached=True)
    monkeypatch.setattr(transcription.transcribe, "get_whisper_model", lambda: whisper)
    _patch_audio_decode(monkeypatch, 3.0)
    monkeypatch.setattr(config, "resolve_storage_path", lambda _path: audio_file)

    resp = client.post(
        "/transcribe/subtitles",
        data={"generation_id": "gen-1", "language": "en", "model": "base"},
    )
    assert resp.status_code == 200

    payload = resp.json()
    assert payload["text"] == "hello world"
    assert payload["duration"] == 3.0
    assert payload["segments"] == [
        {"index": 0, "start": 0.0, "end": 1.2, "text": "hello"},
        {"index": 1, "start": 1.2, "end": 2.0, "text": "world"},
    ]

    db.close()
    engine.dispose()


def test_subtitles_success_with_sample_id(monkeypatch, tmp_path):
    """sample_id path should transcribe and return text/duration/segments payload."""
    engine, session_local = _create_db(tmp_path)
    db = session_local()
    client = _build_test_client(db)

    audio_file = tmp_path / "sample.wav"
    audio_file.write_bytes(b"dummy")
    _seed_sample(db, sample_id="sample-1", audio_path="profiles/profile-1/samples/sample-1.wav")

    whisper = DummyWhisperBackend(cached=True)
    monkeypatch.setattr(transcription.transcribe, "get_whisper_model", lambda: whisper)
    _patch_audio_decode(monkeypatch, 2.0)
    monkeypatch.setattr(config, "resolve_storage_path", lambda _path: audio_file)

    resp = client.post(
        "/transcribe/subtitles",
        data={"sample_id": "sample-1", "language": "en", "model": "base"},
    )
    assert resp.status_code == 200

    payload = resp.json()
    assert payload["text"] == "hello world"
    assert payload["duration"] == 2.0
    assert payload["segments"] == [
        {"index": 0, "start": 0.0, "end": 1.2, "text": "hello"},
        {"index": 1, "start": 1.2, "end": 2.0, "text": "world"},
    ]

    db.close()
    engine.dispose()


def test_subtitles_model_not_cached_returns_202(monkeypatch, tmp_path):
    """Uncached whisper model should trigger background download and return 202."""
    engine, session_local = _create_db(tmp_path)
    db = session_local()
    client = _build_test_client(db)

    whisper = DummyWhisperBackend(cached=False)
    monkeypatch.setattr(transcription.transcribe, "get_whisper_model", lambda: whisper)
    _patch_audio_decode(monkeypatch, 1.0)

    resp = client.post(
        "/transcribe/subtitles",
        data={"model": "base"},
        files={"file": ("audio.wav", b"dummy", "audio/wav")},
    )

    assert resp.status_code == 202
    detail = resp.json()["detail"]
    assert detail["downloading"] is True
    assert detail["model_name"] == "whisper-base"
    assert whisper.transcribe_with_segments_called is False

    db.close()
    engine.dispose()


def test_subtitles_zh_restores_punctuation(monkeypatch, tmp_path):
    """Chinese subtitles should restore punctuation in text and segment payload."""
    engine, session_local = _create_db(tmp_path)
    db = session_local()
    client = _build_test_client(db)

    audio_file = tmp_path / "sample.wav"
    audio_file.write_bytes(b"dummy")
    _seed_sample(db, sample_id="sample-1", audio_path="profiles/profile-1/samples/sample-1.wav")

    whisper = DummyWhisperBackend(
        cached=True,
        detailed_text="你好世界",
        detailed_segments=[
            {"index": 0, "start": 0.0, "end": 1.0, "text": "你好"},
            {"index": 1, "start": 1.0, "end": 2.0, "text": "世界"},
        ],
    )
    punctuator = DummyPunctuationBackend(cached=True)

    monkeypatch.setattr(transcription.transcribe, "get_whisper_model", lambda: whisper)
    monkeypatch.setattr(transcription.punctuation, "get_punctuation_restorer", lambda: punctuator)
    monkeypatch.setattr(config, "resolve_storage_path", lambda _path: audio_file)
    _patch_audio_decode(monkeypatch, 2.0)

    resp = _post_subtitles(client, sample_id="sample-1", language="zh")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["text"] == "你好世界。"
    assert payload["segments"][0]["text"] == "你好。"
    assert payload["segments"][1]["text"] == "世界。"
    assert punctuator.restore_text_called is True
    assert punctuator.restore_segments_called is True

    db.close()
    engine.dispose()


def test_subtitles_auto_cjk_restores_punctuation(monkeypatch, tmp_path):
    """Auto language should restore punctuation for detected CJK text."""
    engine, session_local = _create_db(tmp_path)
    db = session_local()
    client = _build_test_client(db)

    audio_file = tmp_path / "sample.wav"
    audio_file.write_bytes(b"dummy")
    _seed_sample(db, sample_id="sample-1", audio_path="profiles/profile-1/samples/sample-1.wav")

    whisper = DummyWhisperBackend(
        cached=True,
        detailed_text="今天开会结束",
        detailed_segments=[{"index": 0, "start": 0.0, "end": 1.0, "text": "今天开会结束"}],
    )
    punctuator = DummyPunctuationBackend(cached=True)

    monkeypatch.setattr(transcription.transcribe, "get_whisper_model", lambda: whisper)
    monkeypatch.setattr(transcription.punctuation, "get_punctuation_restorer", lambda: punctuator)
    monkeypatch.setattr(config, "resolve_storage_path", lambda _path: audio_file)
    _patch_audio_decode(monkeypatch, 1.0)

    resp = _post_subtitles(client, sample_id="sample-1")
    assert resp.status_code == 200
    assert resp.json()["text"] == "今天开会结束。"
    assert punctuator.restore_text_called is True

    db.close()
    engine.dispose()


def test_subtitles_en_skips_punctuation(monkeypatch, tmp_path):
    """Non-Chinese language should skip punctuation restoration."""
    engine, session_local = _create_db(tmp_path)
    db = session_local()
    client = _build_test_client(db)

    audio_file = tmp_path / "sample.wav"
    audio_file.write_bytes(b"dummy")
    _seed_sample(db, sample_id="sample-1", audio_path="profiles/profile-1/samples/sample-1.wav")

    whisper = DummyWhisperBackend(
        cached=True,
        detailed_text="今天开会结束",
        detailed_segments=[{"index": 0, "start": 0.0, "end": 1.0, "text": "今天开会结束"}],
    )
    punctuator = DummyPunctuationBackend(cached=True)

    monkeypatch.setattr(transcription.transcribe, "get_whisper_model", lambda: whisper)
    monkeypatch.setattr(transcription.punctuation, "get_punctuation_restorer", lambda: punctuator)
    monkeypatch.setattr(config, "resolve_storage_path", lambda _path: audio_file)
    _patch_audio_decode(monkeypatch, 1.0)

    resp = _post_subtitles(client, sample_id="sample-1", language="en")
    assert resp.status_code == 200
    assert resp.json()["text"] == "今天开会结束"
    assert punctuator.restore_text_called is False
    assert punctuator.restore_segments_called is False

    db.close()
    engine.dispose()


def test_subtitles_punctuation_model_not_cached_returns_202(monkeypatch, tmp_path):
    """Missing punctuation model should return 202 and trigger download task."""
    engine, session_local = _create_db(tmp_path)
    db = session_local()
    client = _build_test_client(db)

    audio_file = tmp_path / "sample.wav"
    audio_file.write_bytes(b"dummy")
    _seed_sample(db, sample_id="sample-1", audio_path="profiles/profile-1/samples/sample-1.wav")

    whisper = DummyWhisperBackend(
        cached=True,
        detailed_text="你好世界",
        detailed_segments=[{"index": 0, "start": 0.0, "end": 1.0, "text": "你好世界"}],
    )
    punctuator = DummyPunctuationBackend(cached=False)

    monkeypatch.setattr(transcription.transcribe, "get_whisper_model", lambda: whisper)
    monkeypatch.setattr(transcription.punctuation, "get_punctuation_restorer", lambda: punctuator)
    monkeypatch.setattr(config, "resolve_storage_path", lambda _path: audio_file)
    _patch_audio_decode(monkeypatch, 1.0)

    resp = _post_subtitles(client, sample_id="sample-1", language="zh")
    assert resp.status_code == 202
    detail = resp.json()["detail"]
    assert detail["downloading"] is True
    assert detail["model_name"] == "punc-ct-transformer-zh-cn"

    db.close()
    engine.dispose()


def test_subtitles_punctuation_failure_returns_500(monkeypatch, tmp_path):
    """Punctuation restoration should fail request when restoration raises."""
    engine, session_local = _create_db(tmp_path)
    db = session_local()
    client = _build_test_client(db)

    audio_file = tmp_path / "sample.wav"
    audio_file.write_bytes(b"dummy")
    _seed_sample(db, sample_id="sample-1", audio_path="profiles/profile-1/samples/sample-1.wav")

    whisper = DummyWhisperBackend(
        cached=True,
        detailed_text="你好世界",
        detailed_segments=[{"index": 0, "start": 0.0, "end": 1.0, "text": "你好世界"}],
    )
    punctuator = DummyPunctuationBackend(cached=True, fail=True)

    monkeypatch.setattr(transcription.transcribe, "get_whisper_model", lambda: whisper)
    monkeypatch.setattr(transcription.punctuation, "get_punctuation_restorer", lambda: punctuator)
    monkeypatch.setattr(config, "resolve_storage_path", lambda _path: audio_file)
    _patch_audio_decode(monkeypatch, 1.0)

    resp = _post_subtitles(client, sample_id="sample-1", language="zh")
    assert resp.status_code == 500
    assert "Punctuation restoration failed" in resp.json()["detail"]

    db.close()
    engine.dispose()


def test_transcribe_zh_restores_punctuation(monkeypatch, tmp_path):
    """Chinese /transcribe should restore punctuation."""
    engine, session_local = _create_db(tmp_path)
    db = session_local()
    client = _build_test_client(db)

    whisper = DummyWhisperBackend(cached=True, plain_text="你好世界")
    punctuator = DummyPunctuationBackend(cached=True)

    monkeypatch.setattr(transcription.transcribe, "get_whisper_model", lambda: whisper)
    monkeypatch.setattr(transcription.punctuation, "get_punctuation_restorer", lambda: punctuator)
    _patch_audio_decode(monkeypatch, 1.0)

    resp = _post_transcribe(client, language="zh")
    assert resp.status_code == 200
    assert resp.json()["text"] == "你好世界。"
    assert punctuator.restore_text_called is True

    db.close()
    engine.dispose()


def test_transcribe_auto_cjk_restores_punctuation(monkeypatch, tmp_path):
    """Auto language /transcribe should restore punctuation for CJK text."""
    engine, session_local = _create_db(tmp_path)
    db = session_local()
    client = _build_test_client(db)

    whisper = DummyWhisperBackend(cached=True, plain_text="今天开会结束")
    punctuator = DummyPunctuationBackend(cached=True)

    monkeypatch.setattr(transcription.transcribe, "get_whisper_model", lambda: whisper)
    monkeypatch.setattr(transcription.punctuation, "get_punctuation_restorer", lambda: punctuator)
    _patch_audio_decode(monkeypatch, 1.0)

    resp = _post_transcribe(client)
    assert resp.status_code == 200
    assert resp.json()["text"] == "今天开会结束。"
    assert punctuator.restore_text_called is True

    db.close()
    engine.dispose()


def test_transcribe_en_skips_punctuation(monkeypatch, tmp_path):
    """English /transcribe should skip punctuation restoration."""
    engine, session_local = _create_db(tmp_path)
    db = session_local()
    client = _build_test_client(db)

    whisper = DummyWhisperBackend(cached=True, plain_text="今天开会结束")
    punctuator = DummyPunctuationBackend(cached=True)

    monkeypatch.setattr(transcription.transcribe, "get_whisper_model", lambda: whisper)
    monkeypatch.setattr(transcription.punctuation, "get_punctuation_restorer", lambda: punctuator)
    _patch_audio_decode(monkeypatch, 1.0)

    resp = _post_transcribe(client, language="en")
    assert resp.status_code == 200
    assert resp.json()["text"] == "今天开会结束"
    assert punctuator.restore_text_called is False

    db.close()
    engine.dispose()


def test_transcribe_punctuation_model_not_cached_returns_202(monkeypatch, tmp_path):
    """Missing punctuation model should return 202 for Chinese /transcribe."""
    engine, session_local = _create_db(tmp_path)
    db = session_local()
    client = _build_test_client(db)

    whisper = DummyWhisperBackend(cached=True, plain_text="你好世界")
    punctuator = DummyPunctuationBackend(cached=False)

    monkeypatch.setattr(transcription.transcribe, "get_whisper_model", lambda: whisper)
    monkeypatch.setattr(transcription.punctuation, "get_punctuation_restorer", lambda: punctuator)
    _patch_audio_decode(monkeypatch, 1.0)

    resp = _post_transcribe(client, language="zh")
    assert resp.status_code == 202
    detail = resp.json()["detail"]
    assert detail["downloading"] is True
    assert detail["model_name"] == "punc-ct-transformer-zh-cn"

    db.close()
    engine.dispose()


def test_transcribe_punctuation_failure_returns_500(monkeypatch, tmp_path):
    """Punctuation restore failure should return 500 on /transcribe."""
    engine, session_local = _create_db(tmp_path)
    db = session_local()
    client = _build_test_client(db)

    whisper = DummyWhisperBackend(cached=True, plain_text="你好世界")
    punctuator = DummyPunctuationBackend(cached=True, fail=True)

    monkeypatch.setattr(transcription.transcribe, "get_whisper_model", lambda: whisper)
    monkeypatch.setattr(transcription.punctuation, "get_punctuation_restorer", lambda: punctuator)
    _patch_audio_decode(monkeypatch, 1.0)

    resp = _post_transcribe(client, language="zh")
    assert resp.status_code == 500
    assert "Punctuation restoration failed" in resp.json()["detail"]

    db.close()
    engine.dispose()


def test_transcribe_punctuation_disabled_skips_restoration(monkeypatch, tmp_path):
    """Global punctuation toggle off should bypass restoration even for zh."""
    engine, session_local = _create_db(tmp_path)
    db = session_local()
    client = _build_test_client(db)

    whisper = DummyWhisperBackend(cached=True, plain_text="你好世界")
    punctuator = DummyPunctuationBackend(cached=True)

    monkeypatch.setattr(config, "ENABLE_PUNCTUATION_RESTORATION", False)
    monkeypatch.setattr(transcription.transcribe, "get_whisper_model", lambda: whisper)
    monkeypatch.setattr(transcription.punctuation, "get_punctuation_restorer", lambda: punctuator)
    _patch_audio_decode(monkeypatch, 1.0)

    resp = _post_transcribe(client, language="zh")
    assert resp.status_code == 200
    assert resp.json()["text"] == "你好世界"
    assert punctuator.restore_text_called is False

    db.close()
    engine.dispose()


def test_transcribe_existing_punctuation_skips_restoration(monkeypatch, tmp_path):
    """Text that already has punctuation should not be restored again."""
    engine, session_local = _create_db(tmp_path)
    db = session_local()
    client = _build_test_client(db)

    whisper = DummyWhisperBackend(cached=True, plain_text="你好。世界。")
    punctuator = DummyPunctuationBackend(cached=True)

    monkeypatch.setattr(transcription.transcribe, "get_whisper_model", lambda: whisper)
    monkeypatch.setattr(transcription.punctuation, "get_punctuation_restorer", lambda: punctuator)
    _patch_audio_decode(monkeypatch, 1.0)

    resp = _post_transcribe(client, language="zh")
    assert resp.status_code == 200
    assert resp.json()["text"] == "你好。世界。"
    assert punctuator.restore_text_called is False

    db.close()
    engine.dispose()


def test_subtitles_existing_punctuation_skips_restoration(monkeypatch, tmp_path):
    """Subtitles with existing punctuation should skip punctuation restore."""
    engine, session_local = _create_db(tmp_path)
    db = session_local()
    client = _build_test_client(db)

    audio_file = tmp_path / "sample.wav"
    audio_file.write_bytes(b"dummy")
    _seed_sample(db, sample_id="sample-1", audio_path="profiles/profile-1/samples/sample-1.wav")

    whisper = DummyWhisperBackend(
        cached=True,
        detailed_text="你好。世界。",
        detailed_segments=[
            {"index": 0, "start": 0.0, "end": 1.0, "text": "你好。"},
            {"index": 1, "start": 1.0, "end": 2.0, "text": "世界。"},
        ],
    )
    punctuator = DummyPunctuationBackend(cached=True)

    monkeypatch.setattr(transcription.transcribe, "get_whisper_model", lambda: whisper)
    monkeypatch.setattr(transcription.punctuation, "get_punctuation_restorer", lambda: punctuator)
    monkeypatch.setattr(config, "resolve_storage_path", lambda _path: audio_file)
    _patch_audio_decode(monkeypatch, 2.0)

    resp = _post_subtitles(client, sample_id="sample-1", language="zh")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["text"] == "你好。世界。"
    assert payload["segments"][0]["text"] == "你好。"
    assert payload["segments"][1]["text"] == "世界。"
    assert punctuator.restore_text_called is False
    assert punctuator.restore_segments_called is False

    db.close()
    engine.dispose()
