"""
CUDA backend download, assembly, and verification.

Downloads two archives from GitHub Releases:
  1. Server core (voicebox-server-cuda.tar.gz) — the exe + non-NVIDIA deps,
     versioned with the app.
  2. CUDA libs (cuda-libs-{version}.tar.gz) — NVIDIA runtime libraries,
     versioned independently (only redownloaded on CUDA toolkit bump).

Both archives are extracted into {data_dir}/backends/cuda/ which forms the
complete PyInstaller --onedir directory structure that torch expects.
Downloaded archives are cached directly in {data_dir}/backends/cuda/ as:
  - .download-CUDA-server.tmp
  - .download-CUDA-libraries.tmp
Archive source priority:
  1. Existing cache under {data_dir}/backends/cuda/
  2. Development mode: {repo_root}/release-assets/
  3. Frozen mode: install-dir probe (exe dir, parent, grandparent + release-assets)
  4. GitHub release download fallback
"""

import asyncio
import json
import logging
import os
import shutil
import sys
import tarfile
from pathlib import Path

from .. import __version__
from ..config import get_data_dir
from ..utils.progress import get_progress_manager

logger = logging.getLogger(__name__)

GITHUB_RELEASES_URL = "https://github.com/jamiepine/voicebox/releases/download"

PROGRESS_KEY = "cuda-backend"

# The current expected CUDA libs version.  Bump this when we change the
# CUDA toolkit version or torch's CUDA dependency changes (e.g. cu126 -> cu128).
CUDA_LIBS_VERSION = "cu128-v1"

# Prevents concurrent download_cuda_binary() calls from racing on the same
# temp file.  The auto-update background task and the manual HTTP endpoint
# can both invoke download_cuda_binary(); without this lock the progress-
# manager status check is a TOCTOU race.
_download_lock = asyncio.Lock()


def get_backends_dir() -> Path:
    """Directory where downloaded backend binaries are stored."""
    d = get_data_dir() / "backends"
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_cuda_dir() -> Path:
    """Directory where the CUDA backend (onedir) is extracted."""
    d = get_backends_dir() / "cuda"
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_cuda_exe_name() -> str:
    """Platform-specific CUDA executable filename."""
    if sys.platform == "win32":
        return "voicebox-server-cuda.exe"
    return "voicebox-server-cuda"


def get_cuda_binary_path() -> Path | None:
    """Return path to the CUDA executable if it exists inside the onedir."""
    p = get_cuda_dir() / get_cuda_exe_name()
    if p.exists():
        return p
    return None


def get_cuda_libs_manifest_path() -> Path:
    """Path to the cuda-libs.json manifest inside the CUDA dir."""
    return get_cuda_dir() / "cuda-libs.json"


def get_installed_cuda_libs_version() -> str | None:
    """Read the installed CUDA libs version from cuda-libs.json, or None."""
    manifest_path = get_cuda_libs_manifest_path()
    if not manifest_path.exists():
        return None
    try:
        data = json.loads(manifest_path.read_text())
        return data.get("version")
    except Exception as e:
        logger.warning(f"Could not read cuda-libs.json: {e}")
        return None


def is_cuda_active() -> bool:
    """Check if the current process is the CUDA binary.

    The CUDA binary sets this env var on startup (see server.py).
    """
    return os.environ.get("VOICEBOX_BACKEND_VARIANT") == "cuda"


def get_cuda_status() -> dict:
    """Get current CUDA backend status for the API."""
    progress_manager = get_progress_manager()
    cuda_path = get_cuda_binary_path()
    progress = progress_manager.get_progress(PROGRESS_KEY)
    cuda_libs_version = get_installed_cuda_libs_version()

    return {
        "available": cuda_path is not None,
        "active": is_cuda_active(),
        "binary_path": str(cuda_path) if cuda_path else None,
        "cuda_libs_version": cuda_libs_version,
        "downloading": progress is not None and progress.get("status") == "downloading",
        "download_progress": progress,
    }


def _needs_server_download(version: str | None = None) -> bool:
    """Check if the server core archive needs to be (re)downloaded."""
    cuda_path = get_cuda_binary_path()
    if not cuda_path:
        return True
    # Check if the binary version matches the expected app version
    installed = get_cuda_binary_version()
    expected = version or __version__
    if expected.startswith("v"):
        expected = expected[1:]
    return installed != expected


def _needs_cuda_libs_download() -> bool:
    """Check if the CUDA libs archive needs to be (re)downloaded."""
    installed = get_installed_cuda_libs_version()
    if installed is None:
        return True
    return installed != CUDA_LIBS_VERSION


def _is_frozen_runtime() -> bool:
    """Whether this process is running from a frozen executable."""
    return bool(getattr(sys, "frozen", False))


def _get_repo_root() -> Path:
    """Repository root for development-mode local archive lookup."""
    return Path(__file__).resolve().parents[2]


def _get_archive_cache_path(dest_dir: Path, label: str) -> Path:
    """Canonical cache file path for an archive label."""
    return dest_dir / f".download-{label.replace(' ', '-')}.tmp"


def _iter_install_search_dirs() -> list[Path]:
    """Directories to probe for local archives in frozen/runtime installs."""
    exe_dir = Path(sys.executable).resolve().parent
    levels = [exe_dir, exe_dir.parent, exe_dir.parent.parent]
    seen: set[Path] = set()
    candidates: list[Path] = []

    for base in levels:
        for candidate in (base, base / "release-assets"):
            resolved = candidate.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            candidates.append(resolved)

    return candidates


def _find_local_archive_source(archive_name: str, cache_path: Path) -> tuple[Path | None, str | None]:
    """Resolve the best available local source archive for this run."""
    if cache_path.exists():
        return cache_path, "cache"

    if not _is_frozen_runtime():
        dev_archive = _get_repo_root() / "release-assets" / archive_name
        if dev_archive.exists():
            return dev_archive, "dev-release-assets"
        return None, None

    for base_dir in _iter_install_search_dirs():
        archive_path = base_dir / archive_name
        if archive_path.exists():
            return archive_path, "install-dir"

    return None, None


def _extract_archive(archive_path: Path, dest_dir: Path, label: str, progress_offset: int, total_size: int, current: int) -> None:
    """Extract a .tar.gz archive into dest_dir."""
    progress = get_progress_manager()
    progress.update_progress(
        PROGRESS_KEY,
        current=progress_offset + current,
        total=total_size,
        filename=f"Extracting {label}...",
        status="downloading",
    )
    with tarfile.open(archive_path, "r:gz") as tar:
        if sys.version_info >= (3, 12):  # noqa: UP036
            tar.extractall(path=dest_dir, filter="data")
        else:
            tar.extractall(path=dest_dir)


async def _download_and_extract_archive(
    client,
    url: str,
    archive_name: str,
    dest_dir: Path,
    label: str,
    progress_offset: int,
    total_size: int,
):
    """Download a .tar.gz archive and extract it into dest_dir.

    Args:
        client: httpx.AsyncClient
        url: URL of the .tar.gz archive
        archive_name: Archive file name
        dest_dir: Directory to extract into
        label: Human-readable label for progress updates
        progress_offset: Byte offset for progress reporting (when downloading
            multiple archives sequentially)
        total_size: Total bytes across all downloads (for progress bar)
    """
    progress = get_progress_manager()
    cache_path = _get_archive_cache_path(dest_dir, label)
    temp_path = cache_path.with_suffix(cache_path.suffix + ".part")

    local_path, local_source = _find_local_archive_source(archive_name, cache_path)
    if local_path is not None:
        try:
            if local_source != "cache":
                progress.update_progress(
                    PROGRESS_KEY,
                    current=progress_offset,
                    total=total_size,
                    filename=f"Preparing local {label} package ({local_source})",
                    status="downloading",
                )
                if temp_path.exists():
                    temp_path.unlink()
                shutil.copyfile(local_path, temp_path)
                temp_path.replace(cache_path)
                local_path = cache_path
            local_size = local_path.stat().st_size
            progress.update_progress(
                PROGRESS_KEY,
                current=progress_offset + local_size,
                total=total_size,
                filename=f"Using {label} from {local_source}",
                status="downloading",
            )
            _extract_archive(local_path, dest_dir, label, progress_offset, total_size, local_size)
            logger.info("%s: extracted from local source (%s): %s", label, local_source, local_path)
            return local_size
        except Exception as local_error:
            # Prefer cleaning staged cache copies to avoid deleting release artifacts.
            if temp_path.exists():
                temp_path.unlink()
            if cache_path.exists():
                cache_path.unlink(missing_ok=True)
            logger.warning(
                "%s: local source (%s) failed (%s). Falling back to GitHub download.",
                label,
                local_source,
                local_error,
            )
            progress.update_progress(
                PROGRESS_KEY,
                current=progress_offset,
                total=total_size,
                filename=f"Local {label} package failed; downloading fallback",
                status="downloading",
            )

    downloaded = 0
    try:
        if temp_path.exists():
            temp_path.unlink()

        async with client.stream("GET", url) as response:
            response.raise_for_status()
            with open(temp_path, "wb") as f:
                async for chunk in response.aiter_bytes(chunk_size=1024 * 1024):
                    f.write(chunk)
                    downloaded += len(chunk)
                    progress.update_progress(
                        PROGRESS_KEY,
                        current=progress_offset + downloaded,
                        total=total_size,
                        filename=f"Downloading {label} from github",
                        status="downloading",
                    )

        temp_path.replace(cache_path)
        logger.info("%s: downloaded from github and cached at %s", label, cache_path)
        _extract_archive(cache_path, dest_dir, label, progress_offset, total_size, downloaded)
        logger.info("%s: extracted to %s", label, dest_dir)
    finally:
        if temp_path.exists():
            temp_path.unlink()

    if downloaded == 0 and cache_path.exists():
        downloaded = cache_path.stat().st_size
    return downloaded


async def download_cuda_binary(version: str | None = None):
    """Download the CUDA backend (server core + CUDA libs if needed).

    Downloads both archives from GitHub Releases, extracts them into
    {data_dir}/backends/cuda/, and writes the cuda-libs.json manifest.

    Only downloads what's needed:
    - Server core: always redownloaded (versioned with app)
    - CUDA libs: only if missing or version mismatch

    Args:
        version: Version tag (e.g. "v0.3.0"). Defaults to current app version.
    """
    if _download_lock.locked():
        logger.info("CUDA download already in progress, skipping duplicate request")
        return
    async with _download_lock:
        await _download_cuda_binary_locked(version)


async def _download_cuda_binary_locked(version: str | None = None):
    """Inner implementation of download_cuda_binary, called under _download_lock."""
    import httpx

    if version is None:
        version = f"v{__version__}"

    progress = get_progress_manager()
    cuda_dir = get_cuda_dir()

    need_server = _needs_server_download(version)
    need_libs = _needs_cuda_libs_download()

    if not need_server and not need_libs:
        logger.info("CUDA backend is up to date, nothing to download")
        return

    logger.info(
        f"Starting CUDA backend download for {version} "
        f"(server={'yes' if need_server else 'cached'}, "
        f"libs={'yes' if need_libs else 'cached'})"
    )
    progress.update_progress(
        PROGRESS_KEY,
        current=0,
        total=0,
        filename="Preparing download...",
        status="downloading",
    )

    base_url = f"{GITHUB_RELEASES_URL}/{version}"
    server_archive = "voicebox-server-cuda.tar.gz"
    libs_archive = f"cuda-libs-{CUDA_LIBS_VERSION}.tar.gz"

    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
            # Estimate total download size
            total_size = 0
            if need_server:
                server_cache = _get_archive_cache_path(cuda_dir, "CUDA server")
                server_local, _ = _find_local_archive_source(server_archive, server_cache)
                if server_local is not None:
                    total_size += server_local.stat().st_size
                else:
                    try:
                        head = await client.head(f"{base_url}/{server_archive}")
                        total_size += int(head.headers.get("content-length", 0))
                    except Exception:
                        pass
            if need_libs:
                libs_cache = _get_archive_cache_path(cuda_dir, "CUDA libraries")
                libs_local, _ = _find_local_archive_source(libs_archive, libs_cache)
                if libs_local is not None:
                    total_size += libs_local.stat().st_size
                else:
                    try:
                        head = await client.head(f"{base_url}/{libs_archive}")
                        total_size += int(head.headers.get("content-length", 0))
                    except Exception:
                        pass

            logger.info(f"Total download size: {total_size / 1024 / 1024:.1f} MB")

            offset = 0

            # Download server core
            if need_server:
                server_downloaded = await _download_and_extract_archive(
                    client,
                    url=f"{base_url}/{server_archive}",
                    archive_name=server_archive,
                    dest_dir=cuda_dir,
                    label="CUDA server",
                    progress_offset=offset,
                    total_size=total_size,
                )
                offset += server_downloaded

                # Make executable on Unix
                exe_path = cuda_dir / get_cuda_exe_name()
                if sys.platform != "win32" and exe_path.exists():
                    exe_path.chmod(0o755)

            # Download CUDA libs
            if need_libs:
                await _download_and_extract_archive(
                    client,
                    url=f"{base_url}/{libs_archive}",
                    archive_name=libs_archive,
                    dest_dir=cuda_dir,
                    label="CUDA libraries",
                    progress_offset=offset,
                    total_size=total_size,
                )

                # Write local cuda-libs.json manifest
                manifest = {"version": CUDA_LIBS_VERSION}
                get_cuda_libs_manifest_path().write_text(json.dumps(manifest, indent=2) + "\n")

        logger.info(f"CUDA backend ready at {cuda_dir}")
        progress.mark_complete(PROGRESS_KEY)

    except Exception as e:
        logger.error(f"CUDA backend download failed: {e}")
        progress.mark_error(PROGRESS_KEY, str(e))
        raise


def get_cuda_binary_version() -> str | None:
    """Get the version of the installed CUDA binary, or None if not installed."""
    import subprocess

    cuda_path = get_cuda_binary_path()
    if not cuda_path:
        return None
    try:
        result = subprocess.run(
            [str(cuda_path), "--version"],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(cuda_path.parent),  # Run from the onedir directory
        )
        # Output format: "voicebox-server 0.3.0"
        for line in result.stdout.strip().splitlines():
            if "voicebox-server" in line:
                return line.split()[-1]
    except Exception as e:
        logger.warning(f"Could not get CUDA binary version: {e}")
    return None


async def check_and_update_cuda_binary():
    """Check if the CUDA binary is outdated and auto-download if so.

    Called on server startup. Checks both server version and CUDA libs
    version. Downloads only what's needed.
    """
    cuda_path = get_cuda_binary_path()
    if not cuda_path:
        return  # No CUDA binary installed, nothing to update

    need_server = _needs_server_download()
    need_libs = _needs_cuda_libs_download()

    if not need_server and not need_libs:
        logger.info(f"CUDA binary is up to date (server=v{__version__}, libs={get_installed_cuda_libs_version()})")
        return

    reasons = []
    if need_server:
        cuda_version = get_cuda_binary_version()
        reasons.append(f"server v{cuda_version} != v{__version__}")
    if need_libs:
        installed_libs = get_installed_cuda_libs_version()
        reasons.append(f"libs {installed_libs} != {CUDA_LIBS_VERSION}")

    logger.info(f"CUDA backend needs update ({', '.join(reasons)}). Auto-downloading...")

    try:
        await download_cuda_binary()
    except Exception as e:
        logger.error(f"Auto-update of CUDA binary failed: {e}")


async def delete_cuda_binary() -> bool:
    """Delete the downloaded CUDA backend directory. Returns True if deleted."""
    import shutil

    cuda_dir = get_cuda_dir()
    if cuda_dir.exists() and any(cuda_dir.iterdir()):
        shutil.rmtree(cuda_dir)
        logger.info(f"Deleted CUDA backend directory: {cuda_dir}")
        return True
    return False
