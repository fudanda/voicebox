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
LOCAL_COPY_CHUNK_SIZE = 1024 * 1024 * 4
NETWORK_DOWNLOAD_CHUNK_SIZE = 1024 * 1024

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
        "downloading": progress is not None and progress.get("status") in {"downloading", "extracting"},
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


def _compute_progress_percent(current_work: int, total_work: int) -> float | None:
    """Convert aggregate work units into a UI-friendly percentage."""
    if total_work <= 0:
        return None
    return min(100.0, max(0.0, (current_work / total_work) * 100))


def _copy_file_with_progress(
    src_path: Path,
    dest_path: Path,
    *,
    label: str,
    source_name: str,
    progress_offset: int,
    total_work: int,
    archive_size: int,
) -> int:
    """Copy a local archive into the cache with chunked progress updates."""
    progress = get_progress_manager()
    copied = 0

    with src_path.open("rb") as src, dest_path.open("wb") as dest:
        while chunk := src.read(LOCAL_COPY_CHUNK_SIZE):
            dest.write(chunk)
            copied += len(chunk)
            progress.update_progress(
                PROGRESS_KEY,
                current=copied,
                total=archive_size,
                filename=f"Copying local {label} package ({source_name})",
                status="downloading",
                progress=_compute_progress_percent(progress_offset + copied, total_work),
            )

    return copied


def _extract_archive(
    archive_path: Path,
    dest_dir: Path,
    *,
    label: str,
    progress_offset: int,
    total_work: int,
    phase_work_size: int,
) -> None:
    """Extract a .tar.gz archive into dest_dir with per-member progress."""
    progress = get_progress_manager()

    with tarfile.open(archive_path, "r:gz") as tar:
        members = tar.getmembers()
        member_units = [member.size if member.size > 0 else 1 for member in members]
        total_extract_units = sum(member_units) or 1
        extracted_units = 0

        progress.update_progress(
            PROGRESS_KEY,
            current=0,
            total=0 if total_work > 0 else total_extract_units,
            filename=f"Extracting {label}...",
            status="extracting",
            progress=_compute_progress_percent(progress_offset, total_work),
        )

        for member, units in zip(members, member_units, strict=False):
            if sys.version_info >= (3, 12):  # noqa: UP036
                tar.extract(member, path=dest_dir, filter="data")
            else:
                tar.extract(member, path=dest_dir)

            extracted_units += units
            progress_override = None
            if total_work > 0:
                phase_ratio = extracted_units / total_extract_units
                current_work = progress_offset + int(phase_work_size * phase_ratio)
                progress_override = _compute_progress_percent(current_work, total_work)

            progress.update_progress(
                PROGRESS_KEY,
                current=0 if progress_override is not None else extracted_units,
                total=0 if progress_override is not None else total_extract_units,
                filename=f"Extracting {label}...",
                status="extracting",
                progress=progress_override,
            )


async def _download_and_extract_archive(
    client,
    url: str,
    archive_name: str,
    dest_dir: Path,
    label: str,
    progress_offset: int,
    total_work: int,
    archive_size: int,
):
    """Download a .tar.gz archive and extract it into dest_dir.

    Args:
        client: httpx.AsyncClient
        url: URL of the .tar.gz archive
        archive_name: Archive file name
        dest_dir: Directory to extract into
        label: Human-readable label for progress updates
        progress_offset: Aggregate work offset for progress reporting
        total_work: Total work units across all archive operations
        archive_size: Compressed archive size in bytes, when known
    """
    progress = get_progress_manager()
    cache_path = _get_archive_cache_path(dest_dir, label)
    temp_path = cache_path.with_suffix(cache_path.suffix + ".part")

    local_path, local_source = _find_local_archive_source(archive_name, cache_path)
    if local_path is not None:
        try:
            local_size = archive_size or local_path.stat().st_size
            transfer_work = 0 if local_source == "cache" else local_size
            extract_work = local_size

            if local_source != "cache":
                if temp_path.exists():
                    temp_path.unlink()
                _copy_file_with_progress(
                    local_path,
                    temp_path,
                    label=label,
                    source_name=local_source,
                    progress_offset=progress_offset,
                    total_work=total_work,
                    archive_size=local_size,
                )
                temp_path.replace(cache_path)
                local_path = cache_path

            progress.update_progress(
                PROGRESS_KEY,
                current=local_size,
                total=local_size,
                filename=f"Using {label} from {local_source}",
                status="downloading",
                progress=_compute_progress_percent(progress_offset + transfer_work, total_work),
            )
            _extract_archive(
                local_path,
                dest_dir,
                label=label,
                progress_offset=progress_offset + transfer_work,
                total_work=total_work,
                phase_work_size=extract_work,
            )
            logger.info("%s: extracted from local source (%s): %s", label, local_source, local_path)
            return transfer_work + extract_work
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
                current=0,
                total=0,
                filename=f"Local {label} package failed; downloading fallback",
                status="downloading",
                progress=_compute_progress_percent(progress_offset, total_work),
            )

    downloaded = 0
    try:
        if temp_path.exists():
            temp_path.unlink()

        async with client.stream("GET", url) as response:
            response.raise_for_status()
            with open(temp_path, "wb") as f:
                async for chunk in response.aiter_bytes(chunk_size=NETWORK_DOWNLOAD_CHUNK_SIZE):
                    f.write(chunk)
                    downloaded += len(chunk)
                    progress.update_progress(
                        PROGRESS_KEY,
                        current=downloaded,
                        total=archive_size or 0,
                        filename=f"Downloading {label} from github",
                        status="downloading",
                        progress=_compute_progress_percent(progress_offset + downloaded, total_work),
                    )

        temp_path.replace(cache_path)
        logger.info("%s: downloaded from github and cached at %s", label, cache_path)
        transfer_work = archive_size or downloaded
        extract_work = archive_size or downloaded
        _extract_archive(
            cache_path,
            dest_dir,
            label=label,
            progress_offset=progress_offset + transfer_work,
            total_work=total_work,
            phase_work_size=extract_work,
        )
        logger.info("%s: extracted to %s", label, dest_dir)
    finally:
        if temp_path.exists():
            temp_path.unlink()

    if downloaded == 0 and cache_path.exists():
        downloaded = cache_path.stat().st_size
    archive_work = archive_size or downloaded
    return archive_work * 2


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
        filename="Preparing CUDA backend...",
        status="downloading",
        progress=0,
    )

    base_url = f"{GITHUB_RELEASES_URL}/{version}"
    server_archive = "voicebox-server-cuda.tar.gz"
    libs_archive = f"cuda-libs-{CUDA_LIBS_VERSION}.tar.gz"

    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
            # Estimate total work across local copy/download + extraction phases.
            total_work = 0
            server_size = 0
            if need_server:
                server_cache = _get_archive_cache_path(cuda_dir, "CUDA server")
                server_local, server_source = _find_local_archive_source(server_archive, server_cache)
                if server_local is not None:
                    server_size = server_local.stat().st_size
                    total_work += server_size if server_source == "cache" else server_size * 2
                else:
                    try:
                        head = await client.head(f"{base_url}/{server_archive}")
                        server_size = int(head.headers.get("content-length", 0))
                        total_work += server_size * 2
                    except Exception:
                        pass
            libs_size = 0
            if need_libs:
                libs_cache = _get_archive_cache_path(cuda_dir, "CUDA libraries")
                libs_local, libs_source = _find_local_archive_source(libs_archive, libs_cache)
                if libs_local is not None:
                    libs_size = libs_local.stat().st_size
                    total_work += libs_size if libs_source == "cache" else libs_size * 2
                else:
                    try:
                        head = await client.head(f"{base_url}/{libs_archive}")
                        libs_size = int(head.headers.get("content-length", 0))
                        total_work += libs_size * 2
                    except Exception:
                        pass

            logger.info(f"Estimated CUDA work size: {total_work / 1024 / 1024:.1f} MB")

            offset = 0

            # Download server core
            if need_server:
                server_work = await _download_and_extract_archive(
                    client,
                    url=f"{base_url}/{server_archive}",
                    archive_name=server_archive,
                    dest_dir=cuda_dir,
                    label="CUDA server",
                    progress_offset=offset,
                    total_work=total_work,
                    archive_size=server_size,
                )
                offset += server_work

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
                    total_work=total_work,
                    archive_size=libs_size,
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
    cuda_dir = get_cuda_dir()
    if cuda_dir.exists() and any(cuda_dir.iterdir()):
        shutil.rmtree(cuda_dir)
        logger.info(f"Deleted CUDA backend directory: {cuda_dir}")
        return True
    return False
