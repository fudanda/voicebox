"""Unit tests for CUDA archive source selection and fallback behavior."""

from __future__ import annotations

import io
import json
import tarfile
from pathlib import Path

import pytest

from backend.services import cuda


def _make_tar_bytes(files: dict[str, bytes]) -> bytes:
    """Create a gzipped tar archive in memory."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for path, data in files.items():
            info = tarfile.TarInfo(path)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return buf.getvalue()


def _write_tar(path: Path, files: dict[str, bytes]) -> bytes:
    """Write a gzipped tar archive to disk and return its bytes."""
    tar_bytes = _make_tar_bytes(files)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(tar_bytes)
    return tar_bytes


def _patch_common_runtime(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, *, need_server: bool, need_libs: bool) -> Path:
    """Patch common runtime hooks so download runs inside tmp_path."""
    data_dir = tmp_path / "data"
    monkeypatch.setattr(cuda, "get_data_dir", lambda: data_dir)
    monkeypatch.setattr(cuda, "_needs_server_download", lambda *_args, **_kwargs: need_server)
    monkeypatch.setattr(cuda, "_needs_cuda_libs_download", lambda: need_libs)
    return data_dir


def _patch_no_network_client(monkeypatch: pytest.MonkeyPatch) -> None:
    """Patch httpx.AsyncClient to fail on any network usage."""
    import httpx

    class _NoNetworkClient:
        def __init__(self, *_args, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, _exc_type, _exc, _tb):
            return False

        async def head(self, url: str):
            raise AssertionError(f"Unexpected network HEAD: {url}")

        def stream(self, method: str, url: str):
            raise AssertionError(f"Unexpected network {method}: {url}")

    monkeypatch.setattr(httpx, "AsyncClient", _NoNetworkClient)


def _patch_recording_client(
    monkeypatch: pytest.MonkeyPatch,
    payload_by_url: dict[str, bytes],
    calls: list[tuple[str, str]],
) -> None:
    """Patch httpx.AsyncClient with an in-memory fake and call recorder."""
    import httpx

    class _HeadResponse:
        def __init__(self, size: int):
            self.headers = {"content-length": str(size)}

        def raise_for_status(self) -> None:
            return None

    class _StreamResponse:
        def __init__(self, data: bytes):
            self._data = data

        async def __aenter__(self):
            return self

        async def __aexit__(self, _exc_type, _exc, _tb):
            return False

        def raise_for_status(self) -> None:
            return None

        async def aiter_bytes(self, chunk_size: int = 1024 * 1024):
            for idx in range(0, len(self._data), chunk_size):
                yield self._data[idx : idx + chunk_size]

    class _RecordingAsyncClient:
        def __init__(self, *_args, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, _exc_type, _exc, _tb):
            return False

        async def head(self, url: str):
            calls.append(("head", url))
            if url not in payload_by_url:
                raise AssertionError(f"Unexpected HEAD URL: {url}")
            return _HeadResponse(len(payload_by_url[url]))

        def stream(self, method: str, url: str):
            calls.append(("stream", url))
            if method != "GET":
                raise AssertionError(f"Unexpected method: {method}")
            if url not in payload_by_url:
                raise AssertionError(f"Unexpected stream URL: {url}")
            return _StreamResponse(payload_by_url[url])

    monkeypatch.setattr(httpx, "AsyncClient", _RecordingAsyncClient)


@pytest.mark.asyncio
async def test_download_prefers_dev_release_assets_without_network(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """Development mode should use repo release-assets and skip network."""
    data_dir = _patch_common_runtime(monkeypatch, tmp_path, need_server=True, need_libs=False)
    repo_root = tmp_path / "repo"
    monkeypatch.setattr(cuda, "_is_frozen_runtime", lambda: False)
    monkeypatch.setattr(cuda, "_get_repo_root", lambda: repo_root)

    _write_tar(
        repo_root / "release-assets" / "voicebox-server-cuda.tar.gz",
        {"voicebox-server-cuda.exe": b"dev-local-server"},
    )
    _patch_no_network_client(monkeypatch)

    await cuda._download_cuda_binary_locked("v9.9.9")

    extracted = data_dir / "backends" / "cuda" / "voicebox-server-cuda.exe"
    assert extracted.exists()
    assert extracted.read_bytes() == b"dev-local-server"


@pytest.mark.asyncio
async def test_download_prefers_install_dir_archive_in_frozen_mode(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """Frozen mode should find local archives near the installed executable."""
    data_dir = _patch_common_runtime(monkeypatch, tmp_path, need_server=True, need_libs=False)

    exe_path = tmp_path / "install" / "app" / "bin" / "voicebox.exe"
    exe_path.parent.mkdir(parents=True, exist_ok=True)
    exe_path.write_bytes(b"")

    monkeypatch.setattr(cuda, "_is_frozen_runtime", lambda: True)
    monkeypatch.setattr(cuda.sys, "executable", str(exe_path), raising=False)

    _write_tar(
        exe_path.parent.parent / "release-assets" / "voicebox-server-cuda.tar.gz",
        {"voicebox-server-cuda.exe": b"install-local-server"},
    )
    _patch_no_network_client(monkeypatch)

    await cuda._download_cuda_binary_locked("v9.9.9")

    extracted = data_dir / "backends" / "cuda" / "voicebox-server-cuda.exe"
    assert extracted.exists()
    assert extracted.read_bytes() == b"install-local-server"


@pytest.mark.asyncio
async def test_download_falls_back_to_github_when_local_missing(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """When no local package exists, download should stream from GitHub."""
    data_dir = _patch_common_runtime(monkeypatch, tmp_path, need_server=True, need_libs=False)
    monkeypatch.setattr(cuda, "_is_frozen_runtime", lambda: False)
    monkeypatch.setattr(cuda, "_get_repo_root", lambda: tmp_path / "missing-repo")

    version = "v1.2.3"
    server_url = f"{cuda.GITHUB_RELEASES_URL}/{version}/voicebox-server-cuda.tar.gz"
    server_payload = _make_tar_bytes({"voicebox-server-cuda.exe": b"github-server"})
    calls: list[tuple[str, str]] = []
    _patch_recording_client(monkeypatch, {server_url: server_payload}, calls)

    await cuda._download_cuda_binary_locked(version)

    extracted = data_dir / "backends" / "cuda" / "voicebox-server-cuda.exe"
    assert extracted.exists()
    assert extracted.read_bytes() == b"github-server"
    assert ("stream", server_url) in calls


@pytest.mark.asyncio
async def test_corrupted_local_cache_falls_back_to_github(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """Invalid local archive should be cleaned and replaced by GitHub fallback."""
    data_dir = _patch_common_runtime(monkeypatch, tmp_path, need_server=True, need_libs=False)
    monkeypatch.setattr(cuda, "_is_frozen_runtime", lambda: False)
    monkeypatch.setattr(cuda, "_get_repo_root", lambda: tmp_path / "missing-repo")

    cuda_dir = data_dir / "backends" / "cuda"
    cuda_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cuda_dir / ".download-CUDA-server.tmp"
    cache_path.write_bytes(b"invalid-tar-bytes")

    version = "v2.0.0"
    server_url = f"{cuda.GITHUB_RELEASES_URL}/{version}/voicebox-server-cuda.tar.gz"
    server_payload = _make_tar_bytes({"voicebox-server-cuda.exe": b"fallback-server"})
    calls: list[tuple[str, str]] = []
    _patch_recording_client(monkeypatch, {server_url: server_payload}, calls)

    await cuda._download_cuda_binary_locked(version)

    extracted = data_dir / "backends" / "cuda" / "voicebox-server-cuda.exe"
    assert extracted.exists()
    assert extracted.read_bytes() == b"fallback-server"
    assert ("stream", server_url) in calls
    assert cache_path.read_bytes() == server_payload


@pytest.mark.asyncio
async def test_download_never_requests_sha256_files(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """CUDA downloader should not request any .sha256 resources."""
    _patch_common_runtime(monkeypatch, tmp_path, need_server=True, need_libs=True)
    monkeypatch.setattr(cuda, "_is_frozen_runtime", lambda: False)
    monkeypatch.setattr(cuda, "_get_repo_root", lambda: tmp_path / "missing-repo")

    version = "v3.0.0"
    server_url = f"{cuda.GITHUB_RELEASES_URL}/{version}/voicebox-server-cuda.tar.gz"
    libs_url = f"{cuda.GITHUB_RELEASES_URL}/{version}/cuda-libs-{cuda.CUDA_LIBS_VERSION}.tar.gz"
    calls: list[tuple[str, str]] = []
    _patch_recording_client(
        monkeypatch,
        {
            server_url: _make_tar_bytes({"voicebox-server-cuda.exe": b"server"}),
            libs_url: _make_tar_bytes({"nvidia/cudart64_12.dll": b"dll"}),
        },
        calls,
    )

    await cuda._download_cuda_binary_locked(version)

    assert calls, "expected at least one network call"
    assert all(not url.endswith(".sha256") for _, url in calls)


@pytest.mark.asyncio
async def test_download_libs_only_writes_manifest_and_preserves_need_flags(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    """need_server/need_libs behavior and libs manifest writing should remain correct."""
    data_dir = _patch_common_runtime(monkeypatch, tmp_path, need_server=False, need_libs=True)
    monkeypatch.setattr(cuda, "_is_frozen_runtime", lambda: False)
    monkeypatch.setattr(cuda, "_get_repo_root", lambda: tmp_path / "missing-repo")

    version = "v4.0.0"
    libs_url = f"{cuda.GITHUB_RELEASES_URL}/{version}/cuda-libs-{cuda.CUDA_LIBS_VERSION}.tar.gz"
    calls: list[tuple[str, str]] = []
    _patch_recording_client(
        monkeypatch,
        {libs_url: _make_tar_bytes({"nvidia/cudart64_12.dll": b"cuda-libs"})},
        calls,
    )

    await cuda._download_cuda_binary_locked(version)

    cuda_dir = data_dir / "backends" / "cuda"
    assert not (cuda_dir / "voicebox-server-cuda.exe").exists()
    assert (cuda_dir / "nvidia" / "cudart64_12.dll").exists()

    manifest_data = json.loads((cuda_dir / "cuda-libs.json").read_text())
    assert manifest_data["version"] == cuda.CUDA_LIBS_VERSION
    assert all("voicebox-server-cuda.tar.gz" not in url for _, url in calls)

