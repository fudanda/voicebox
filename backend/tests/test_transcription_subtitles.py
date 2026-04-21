"""Tests for the /transcribe/subtitles endpoint."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend import config
from backend.database.models import Base, ProfileSample as DBProfileSample, VoiceProfile as DBVoiceProfile
from backend.routes import transcription


class DummyWhisperBackend:
    """Minimal STT backend stub for subtitle route tests."""

    def __init__(self, *, cached: bool = True, model_size: str = "base"):
        self._cached = cached
        self.model_size = model_size
        self._loaded = False
        self.transcribe_with_segments_called = False

    def is_loaded(self) -> bool:
        return self._loaded

    def _is_model_cached(self, _model_size: str) -> bool:
        return self._cached

    async def load_model_async(self, model_size: str) -> None:
        self._loaded = True
        self.model_size = model_size

    async def transcribe(self, _audio_path: str, _language: str | None, _model_size: str | None) -> str:
        return "plain text"

    async def transcribe_with_segments(
        self,
        _audio_path: str,
        _language: str | None,
        _model_size: str | None,
    ):
        self.transcribe_with_segments_called = True
        return {
            "text": "hello world",
            "segments": [
                {"index": 0, "start": 0.0, "end": 1.2, "text": "hello"},
                {"index": 1, "start": 1.2, "end": 2.0, "text": "world"},
            ],
        }


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


def _seed_sample(db_session, *, sample_id: str, audio_path: str) -> None:
    profile = DBVoiceProfile(
        id="profile-1",
        name="Profile One",
        language="en",
    )
    sample = DBProfileSample(
        id=sample_id,
        profile_id=profile.id,
        audio_path=audio_path,
        reference_text="sample text",
    )
    db_session.add(profile)
    db_session.add(sample)
    db_session.commit()


def test_subtitles_requires_exactly_one_source(monkeypatch, tmp_path):
    """file and sample_id must be mutually exclusive."""
    engine, session_local = _create_db(tmp_path)
    db = session_local()
    client = _build_test_client(db)

    whisper = DummyWhisperBackend(cached=True)
    monkeypatch.setattr(transcription.transcribe, "get_whisper_model", lambda: whisper)
    monkeypatch.setattr("backend.utils.audio.load_audio", lambda *_args, **_kwargs: ([0.0] * 16000, 16000))

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

    db.close()
    engine.dispose()


def test_subtitles_sample_not_found(monkeypatch, tmp_path):
    """sample_id should return 404 when DB record does not exist."""
    engine, session_local = _create_db(tmp_path)
    db = session_local()
    client = _build_test_client(db)

    whisper = DummyWhisperBackend(cached=True)
    monkeypatch.setattr(transcription.transcribe, "get_whisper_model", lambda: whisper)
    monkeypatch.setattr("backend.utils.audio.load_audio", lambda *_args, **_kwargs: ([0.0] * 16000, 16000))

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
    monkeypatch.setattr("backend.utils.audio.load_audio", lambda *_args, **_kwargs: ([0.0] * 16000, 16000))
    monkeypatch.setattr(config, "resolve_storage_path", lambda _path: tmp_path / "does-not-exist.wav")

    resp = client.post("/transcribe/subtitles", data={"sample_id": "sample-1"})
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Sample audio file not found"

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
    monkeypatch.setattr("backend.utils.audio.load_audio", lambda *_args, **_kwargs: ([0.0] * 32000, 16000))
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
    monkeypatch.setattr("backend.utils.audio.load_audio", lambda *_args, **_kwargs: ([0.0] * 16000, 16000))

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
