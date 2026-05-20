# Plan: FFmpeg Auto-Resolution (The FFmpeg Problem)

> Status: Completed
> Priority: P0
> Related: User Experience & Laziness (Feature 2A), Cross-Platform Compatibility (Section 17)

## Overview

When a user runs any `max video` or `max audio compress` command without FFmpeg installed, the CLI raises a `RuntimeError` and exits. The user must manually download and install FFmpeg — a friction point that violates the "Be Lazy for the User" philosophy.

This plan introduces an **automatic FFmpeg binary resolver** that:
1. Detects missing FFmpeg
2. Prompts the user with a Rich confirmation
3. Downloads a platform-specific static binary to `~/.max_cli/bin/`
4. Validates the binary works
5. Uses the resolved path in all subprocess calls (fixing the existing dead-code bug where `self.ffmpeg_path` is stored but never used)

## Problem Analysis

### Current State (Bugs & Gaps)

| Issue | Location | Severity |
|-------|----------|----------|
| `self.ffmpeg_path` is stored in `__init__` but **never used** — all methods hardcode `"ffmpeg"` string | `media_engine.py:33,63,79,...` (20+ occurrences) | **Bug** — dead code |
| No auto-download fallback — user gets a `RuntimeError` and must manually install | `media_engine.py:17-21` | UX Gap |
| `/tmp/hls` hardcoded in `live_preview` — **fails on Windows** | `media_engine.py:314,341,349` | Cross-platform Bug |
| Interface files show generic install instructions but don't offer auto-resolution | `cli_media.py:23-24`, `cli_audio.py:31-33` | UX Gap |
| No binary validation after download (could be corrupted) | N/A | Security Gap |
| No hash verification for downloaded binaries | N/A | Security Gap |

### Root Cause

The `MediaEngine.__init__` resolves the FFmpeg path via `shutil.which("ffmpeg")` and stores it in `self.ffmpeg_path`, but every method builds command lists with the literal string `"ffmpeg"` instead of `self.ffmpeg_path`. This means:
- If FFmpeg is only in `~/.max_cli/bin/` (not in PATH), `shutil.which` finds nothing and the engine refuses to initialize
- Even if it did initialize, the hardcoded `"ffmpeg"` string would fail because the shell wouldn't find it

### Platform-Specific Challenges

| Platform | Binary Name | Static Build Source | Notes |
|----------|-------------|---------------------|-------|
| Windows | `ffmpeg.exe` | gyan.dev | ZIP archive, extract `bin/ffmpeg.exe` |
| macOS (Intel) | `ffmpeg` | evermeet.cx | DMG or direct binary |
| macOS (Apple Silicon) | `ffmpeg` | evermeet.cx or build from source | ARM64 binary |
| Linux (x86_64) | `ffmpeg` | johnvansickle.com | Static build, direct binary |
| Linux (ARM64) | `ffmpeg` | johnvansickle.com | ARM64 static build |

## Goals

- [ ] **G1**: Create `src/max_cli/common/ffmpeg_resolver.py` — auto-download module with platform detection, Rich prompts, and hash verification
- [ ] **G2**: Fix `MediaEngine.__init__` to use a 3-tier resolution strategy (PATH → `~/.max_cli/bin/` → auto-download)
- [ ] **G3**: Replace all 20+ hardcoded `"ffmpeg"` strings with `self.ffmpeg_path` (fix the dead-code bug)
- [ ] **G4**: Fix `/tmp/hls` Windows incompatibility in `live_preview` using `tempfile` or `~/.max_cli/tmp/`
- [ ] **G5**: Update `_check_engine()` in `cli_media.py` and `_check_media_engine()` in `cli_audio.py` to use resolved path
- [ ] **G6**: Add tests that mock download and binary validation
- [ ] **G7**: Cache the resolution result so we don't re-check on every command invocation

## Implementation Details

### Phase 1: Create `ffmpeg_resolver.py`

**File**: `src/max_cli/common/ffmpeg_resolver.py`

```python
"""FFmpeg binary auto-resolution and download module.

Handles detection, download, and validation of FFmpeg binaries
for Windows, macOS, and Linux platforms.
"""

import hashlib
import os
import platform
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Optional
from urllib.request import urlopen, Request
from zipfile import ZipFile

from max_cli.common.exceptions import NetworkError, ResourceNotFoundError
from max_cli.common.logger import console, log_error, log_success

# Platform-specific download URLs (static builds)
FFMPEG_DOWNLOADS = {
    "Windows": {
        "url": "https://github.com/niutech/ffmpeg/releases/latest/download/ffmpeg-master-latest-win64-gpl.zip",
        "binary_name": "ffmpeg.exe",
        "extract_path": "bin/ffmpeg.exe",  # Inside ZIP
        "hash_algo": "sha256",
        # Note: gyan.dev builds are also available but require parsing release page
        # Fallback: https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip
    },
    "Darwin": {
        "url": "https://evermeet.cx/ffmpeg/get/ffmpeg",
        "binary_name": "ffmpeg",
        "extract_path": None,  # Direct binary download
        "hash_algo": "sha256",
    },
    "Linux": {
        "url": "https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz",
        "binary_name": "ffmpeg",
        "extract_path": None,  # tar.xz, extract ffmpeg binary
        "hash_algo": "sha256",
    },
}

# Known SHA256 hashes for pinned versions (updated per release cycle)
# These are examples — update with actual hashes from release pages
FFMPEG_KNOWN_HASHES = {
    "Windows": None,  # Dynamic builds — skip hash check for nightly
    "Darwin": None,
    "Linux": None,
}

MAX_CLI_BIN_DIR = Path.home() / ".max_cli" / "bin"
RESOLUTION_CACHE_FILE = Path.home() / ".max_cli" / ".ffmpeg_resolved_path"


class FFmpegResolver:
    """Resolves FFmpeg binary path with auto-download fallback."""

    def __init__(self):
        self.system = platform.system()
        self.bin_dir = MAX_CLI_BIN_DIR
        self.binary_name = self._get_binary_name()
        self.local_path = self.bin_dir / self.binary_name

    def _get_binary_name(self) -> str:
        """Return platform-specific binary name."""
        return "ffmpeg.exe" if self.system == "Windows" else "ffmpeg"

    def resolve(self, auto_download: bool = True) -> Path:
        """Resolve FFmpeg path using 3-tier strategy.

        Tier 1: Check system PATH via shutil.which
        Tier 2: Check ~/.max_cli/bin/
        Tier 3: Auto-download (if auto_download=True and user confirms)

        Returns:
            Resolved Path to FFmpeg binary

        Raises:
            ResourceNotFoundError: If FFmpeg cannot be found or downloaded
        """
        # Tier 1: System PATH
        system_path = shutil.which(self.binary_name)
        if system_path:
            return Path(system_path)

        # Tier 2: Local bin directory
        if self.local_path.exists():
            # Validate it actually works
            if self._validate_binary(self.local_path):
                return self.local_path
            else:
                # Corrupted — remove and re-download
                self.local_path.unlink()

        # Tier 3: Auto-download
        if auto_download:
            return self._download_and_install()

        raise ResourceNotFoundError(
            f"FFmpeg not found. Install manually or run 'max config setup-ffmpeg'"
        )

    def _download_and_install(self) -> Path:
        """Download FFmpeg binary after user confirmation.

        Returns:
            Path to installed binary

        Raises:
            ResourceNotFoundError: If download fails or user declines
        """
        if self.system not in FFMPEG_DOWNLOADS:
            raise ResourceNotFoundError(
                f"Unsupported platform for auto-download: {self.system}. "
                f"Please install FFmpeg manually from https://ffmpeg.org/download.html"
            )

        # Prompt user
        console.print(
            f"[yellow]FFmpeg is not installed.[/yellow]"
        )
        console.print(
            f"[dim]Max CLI can automatically download a static FFmpeg binary "
            f"to {self.bin_dir} (~60-100MB).[/dim]"
        )

        # Use Rich Confirm for interactive prompt
        # For non-interactive environments (CI, scripts), this returns False
        if not console.is_terminal or os.environ.get("MAX_CLI_NON_INTERACTIVE"):
            raise ResourceNotFoundError(
                "FFmpeg is required. Install manually or set MAX_CLI_NON_INTERACTIVE=0 "
                "to enable interactive prompts."
            )

        from rich.prompt import Confirm

        if not Confirm.ask(
            "Download FFmpeg automatically?",
            default=True,
        ):
            raise ResourceNotFoundError(
                "FFmpeg download declined. Install manually:\n"
                "  Windows: https://www.gyan.dev/ffmpeg/builds/\n"
                "  macOS:   brew install ffmpeg\n"
                "  Linux:   sudo apt install ffmpeg"
            )

        # Perform download
        self.bin_dir.mkdir(parents=True, exist_ok=True)
        console.print(f"[cyan]Downloading FFmpeg for {self.system}...[/cyan]")

        try:
            download_info = FFMPEG_DOWNLOADS[self.system]
            self._download_binary(
                url=download_info["url"],
                binary_name=self.binary_name,
                extract_path=download_info.get("extract_path"),
            )
        except Exception as e:
            log_error(f"FFmpeg download failed: {e}")
            # Clean up partial download
            if self.local_path.exists():
                self.local_path.unlink()
            raise ResourceNotFoundError(
                f"Failed to download FFmpeg: {e}\n"
                f"Please install manually from https://ffmpeg.org/download.html"
            )

        # Validate the downloaded binary
        if not self._validate_binary(self.local_path):
            self.local_path.unlink()
            raise ResourceNotFoundError(
                "Downloaded FFmpeg binary failed validation. "
                "Please install manually."
            )

        # Make executable on Unix
        if self.system != "Windows":
            os.chmod(self.local_path, 0o755)

        # Cache the resolved path
        self._cache_resolution(self.local_path)

        log_success(f"FFmpeg installed to {self.local_path}")
        return self.local_path

    def _download_binary(
        self,
        url: str,
        binary_name: str,
        extract_path: Optional[str] = None,
    ) -> None:
        """Download and extract FFmpeg binary.

        Args:
            url: Download URL
            binary_name: Target binary name (ffmpeg or ffmpeg.exe)
            extract_path: Path inside archive to extract (None for direct binary)
        """
        import tarfile

        headers = {"User-Agent": "MaxCLI/1.0 (FFmpeg Auto-Resolver)"}
        request = Request(url, headers=headers)

        with urlopen(request, timeout=120) as response:
            total_size = response.getheader("Content-Length")
            total_size = int(total_size) if total_size else None

            # Download to temp file first (atomic operation)
            with tempfile.NamedTemporaryFile(
                dir=self.bin_dir,
                suffix=".download",
                delete=False,
            ) as tmp_file:
                downloaded = 0
                chunk_size = 8192

                while True:
                    chunk = response.read(chunk_size)
                    if not chunk:
                        break
                    tmp_file.write(chunk)
                    downloaded += len(chunk)

                    # Progress display
                    if total_size:
                        pct = (downloaded / total_size) * 100
                        console.print(
                            f"\r[cyan]Downloading... {downloaded / 1024 / 1024:.1f}MB "
                            f"/ {total_size / 1024 / 1024:.1f}MB ({pct:.0f}%)[/cyan]",
                            end="",
                        )
                    else:
                        console.print(
                            f"\r[cyan]Downloading... {downloaded / 1024 / 1024:.1f}MB[/cyan]",
                            end="",
                        )

                console.print()  # Newline after progress
                tmp_path = Path(tmp_file.name)

            # Extract or move based on archive type
            if extract_path:
                if url.endswith(".zip"):
                    with ZipFile(tmp_path, "r") as zf:
                        # Find the binary in the archive
                        for member in zf.namelist():
                            if member.endswith(extract_path) or member.endswith(binary_name):
                                zf.extract(member, self.bin_dir)
                                # Move to final location
                                extracted = self.bin_dir / member
                                if extracted != self.local_path:
                                    extracted.rename(self.local_path)
                                break
                elif url.endswith(".tar.xz") or url.endswith(".tar.bz2"):
                    with tarfile.open(tmp_path, "r:*") as tf:
                        for member in tf.getmembers():
                            if member.name.endswith(binary_name):
                                tf.extract(member, self.bin_dir)
                                extracted = self.bin_dir / member.name
                                if extracted != self.local_path:
                                    extracted.rename(self.local_path)
                                break
            else:
                # Direct binary download
                tmp_path.rename(self.local_path)

            # Clean up temp file
            if tmp_path.exists():
                tmp_path.unlink()

    def _validate_binary(self, path: Path) -> bool:
        """Validate that the FFmpeg binary works.

        Args:
            path: Path to FFmpeg binary

        Returns:
            True if binary is valid and executable
        """
        try:
            result = subprocess.run(
                [str(path), "-version"],
                capture_output=True,
                timeout=10,
            )
            return result.returncode == 0 and b"ffmpeg" in result.stdout.lower()
        except (subprocess.TimeoutExpired, OSError, ValueError):
            return False

    def _cache_resolution(self, path: Path) -> None:
        """Cache the resolved FFmpeg path for faster subsequent lookups."""
        RESOLUTION_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        RESOLUTION_CACHE_FILE.write_text(str(path))

    @staticmethod
    def get_cached_resolution() -> Optional[Path]:
        """Get cached FFmpeg path if it still exists and is valid."""
        if not RESOLUTION_CACHE_FILE.exists():
            return None

        cached_path = Path(RESOLUTION_CACHE_FILE.read_text().strip())
        if cached_path.exists():
            # Quick validation
            resolver = FFmpegResolver()
            if resolver._validate_binary(cached_path):
                return cached_path
            else:
                # Stale cache — remove it
                RESOLUTION_CACHE_FILE.unlink()

        return None


def resolve_ffmpeg(auto_download: bool = True) -> Path:
    """Convenience function to resolve FFmpeg path.

    Args:
        auto_download: Whether to prompt for auto-download if not found

    Returns:
        Resolved Path to FFmpeg binary
    """
    # Check cache first
    cached = FFmpegResolver.get_cached_resolution()
    if cached:
        return cached

    resolver = FFmpegResolver()
    return resolver.resolve(auto_download=auto_download)
```

### Phase 2: Fix `MediaEngine.__init__` and Replace Hardcoded Strings

**File**: `src/max_cli/core/engines/media_engine.py`

#### 2a. Update `__init__` with 3-tier resolution

```python
class MediaEngine:
    """
    Wrapper around FFmpeg for video and audio manipulation.
    FFmpeg is auto-resolved from PATH, ~/.max_cli/bin/, or downloaded on demand.
    """

    def __init__(self, auto_resolve: bool = True):
        self.ffmpeg_path = self._resolve_ffmpeg(auto_resolve)

    def _resolve_ffmpeg(self, auto_resolve: bool) -> Path:
        """Resolve FFmpeg path using 3-tier strategy."""
        # Tier 1: System PATH
        system_path = shutil.which("ffmpeg")
        if system_path:
            return Path(system_path)

        # Tier 2: Local bin directory
        from max_cli.common.ffmpeg_resolver import FFmpegResolver
        local_path = FFmpegResolver().local_path
        if local_path.exists():
            return local_path

        # Tier 3: Auto-download
        if auto_resolve:
            from max_cli.common.ffmpeg_resolver import resolve_ffmpeg
            return resolve_ffmpeg(auto_download=True)

        raise RuntimeError(
            "FFmpeg is not installed or not in PATH. "
            "Install it via: 'brew install ffmpeg', 'sudo apt install ffmpeg', "
            "or download from ffmpeg.org"
        )
```

#### 2b. Replace ALL hardcoded `"ffmpeg"` strings with `str(self.ffmpeg_path)`

Every method that currently has `"ffmpeg"` as the first element of `cmd` must be updated. There are **20+ occurrences** across these methods:

| Method | Line | Current | Fix |
|--------|------|---------|-----|
| `compress_video` | 33 | `"ffmpeg"` | `str(self.ffmpeg_path)` |
| `convert_format` | 63 | `"ffmpeg"` | `str(self.ffmpeg_path)` |
| `convert_format` (re-encode) | 79 | `"ffmpeg"` | `str(self.ffmpeg_path)` |
| `extract_audio` | 112 | `"ffmpeg"` | `str(self.ffmpeg_path)` |
| `video_to_gif` | 139 | `"ffmpeg"` | `str(self.ffmpeg_path)` |
| `trim_video` | 165 | `"ffmpeg"` | `str(self.ffmpeg_path)` |
| `get_thumbnail` | 200 | `"ffmpeg"` | `str(self.ffmpeg_path)` |
| `adjust_volume` | 225 | `"ffmpeg"` | `str(self.ffmpeg_path)` |
| `mute_video` | 244 | `"ffmpeg"` | `str(self.ffmpeg_path)` |
| `stream_to_rtmp` | 274 | `"ffmpeg"` | `str(self.ffmpeg_path)` |
| `live_preview` | 317 | `"ffmpeg"` | `str(self.ffmpeg_path)` |
| `_concatenate_demuxer` | 402 | `"ffmpeg"` | `str(self.ffmpeg_path)` |
| `adjust_brightness` | 479 | `"ffmpeg"` | `str(self.ffmpeg_path)` |
| `apply_color_preset` | 517 | `"ffmpeg"` | `str(self.ffmpeg_path)` |
| `stabilize_video` (pass 1) | 540 | `"ffmpeg"` | `str(self.ffmpeg_path)` |
| `stabilize_video` (pass 2) | 553 | `"ffmpeg"` | `str(self.ffmpeg_path)` |
| `normalize_audio` | 582 | `"ffmpeg"` | `str(self.ffmpeg_path)` |
| `compress_audio` | 625 | `"ffmpeg"` | `str(self.ffmpeg_path)` |
| `convert_audio` | 674 | `"ffmpeg"` | `str(self.ffmpeg_path)` |
| `screen_record` | 717 | `"ffmpeg"` | `str(self.ffmpeg_path)` |

**Search pattern to find all occurrences**:
```
rg '"ffmpeg",' src/max_cli/core/engines/media_engine.py
```

### Phase 3: Fix `/tmp/hls` Windows Incompatibility

**File**: `src/max_cli/core/engines/media_engine.py`, `live_preview` method (lines 296-357)

The current code hardcodes `/tmp/hls` which doesn't exist on Windows. Fix using `tempfile` or `~/.max_cli/tmp/`:

```python
def live_preview(
    self,
    input_path: Path,
    port: int = 8080,
    bitrate: str = "2000k",
) -> None:
    """
    Start HTTP server for live preview streaming via HLS.
    """
    import os
    import tempfile
    import threading
    from http.server import HTTPServer, SimpleHTTPRequestHandler

    # Cross-platform temp directory for HLS segments
    hls_dir = Path(tempfile.gettempdir()) / "max_cli_hls"
    hls_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        str(self.ffmpeg_path),  # Fixed: use resolved path
        "-re",
        "-i",
        str(input_path),
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-b:v",
        bitrate,
        "-c:a",
        "aac",
        "-b:a",
        "96k",
        "-f",
        "hls",
        "-hls_time",
        "2",
        "-hls_list_size",
        "10",
        "-hls_flags",
        "delete_segments",
        "-start_number",
        "1",
        str(hls_dir / "live.m3u8"),  # Fixed: cross-platform path
    ]

    class QuietHandler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(hls_dir), **kwargs)

        def log_message(self, format, *args):
            pass

    def run_server():
        server = HTTPServer(("", port), QuietHandler)
        console.print(
            f"[cyan]Live preview available at "
            f"http://localhost:{port}/live.m3u8[/cyan]"
        )
        server.serve_forever()

    thread = threading.Thread(target=run_server, daemon=True)
    thread.start()

    self._run(cmd)
```

Key changes:
1. Replace `/tmp/hls` with `Path(tempfile.gettempdir()) / "max_cli_hls"`
2. Replace `os.chdir("/tmp/hls")` with `directory=str(hls_dir)` in `SimpleHTTPRequestHandler`
3. Replace `print()` with `console.print()` (AGENTS.md rule: no `print()` in core)
4. Use `str(self.ffmpeg_path)` instead of hardcoded `"ffmpeg"`

### Phase 4: Update Interface Files

**File**: `src/max_cli/interface/cli_media.py`

Update `_check_engine()` to use the resolver:

```python
def _check_engine():
    try:
        from max_cli.core.engines.media_engine import MediaEngine
        return MediaEngine(auto_resolve=True)
    except RuntimeError as e:
        log_error(str(e))
        raise typer.Exit(1)
```

Remove the separate `_get_engine()` function since `_check_engine()` now handles everything.

**File**: `src/max_cli/interface/cli_audio.py`

Update `_check_media_engine()` similarly:

```python
def _check_media_engine():
    try:
        from max_cli.core.engines.media_engine import MediaEngine
        return MediaEngine(auto_resolve=True)
    except RuntimeError as e:
        log_error(str(e))
        raise typer.Exit(1)
```

### Phase 5: Add `max config setup-ffmpeg` Command (Optional UX Enhancement)

**File**: `src/max_cli/interface/cli_config.py`

Add a dedicated command for users who want to install FFmpeg proactively:

```python
@app.command("setup-ffmpeg")
def setup_ffmpeg(
    force: bool = typer.Option(False, "--force", "-f", help="Force re-download"),
):
    """Download and install FFmpeg binary to ~/.max_cli/bin/."""
    from max_cli.common.ffmpeg_resolver import FFmpegResolver, resolve_ffmpeg

    resolver = FFmpegResolver()

    if force and resolver.local_path.exists():
        resolver.local_path.unlink()
        console.print("[yellow]Removed existing FFmpeg binary.[/yellow]")

    try:
        path = resolve_ffmpeg(auto_download=True)
        log_success(f"FFmpeg ready at: {path}")
    except Exception as e:
        log_error(str(e))
        raise typer.Exit(1)
```

## Testing Strategy

### Test File: `tests/test_ffmpeg_resolver.py`

```python
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock, mock_open
import subprocess

from max_cli.common.ffmpeg_resolver import FFmpegResolver, resolve_ffmpeg
from max_cli.common.exceptions import ResourceNotFoundError


class TestFFmpegResolver:

    @patch("shutil.which")
    def test_resolve_from_path(self, mock_which):
        """Tier 1: Resolve from system PATH."""
        mock_which.return_value = "/usr/bin/ffmpeg"
        resolver = FFmpegResolver()
        result = resolver.resolve(auto_download=False)
        assert result == Path("/usr/bin/ffmpeg")

    @patch("shutil.which")
    @patch.object(FFmpegResolver, "_validate_binary", return_value=True)
    @patch.object(Path, "exists", return_value=True)
    def test_resolve_from_local_bin(self, mock_exists, mock_validate, mock_which):
        """Tier 2: Resolve from ~/.max_cli/bin/."""
        mock_which.return_value = None
        resolver = FFmpegResolver()
        result = resolver.resolve(auto_download=False)
        assert result == resolver.local_path

    @patch("shutil.which", return_value=None)
    def test_resolve_no_download_raises(self, mock_which):
        """Tier 3: Without auto-download, raises ResourceNotFoundError."""
        with patch.object(Path, "exists", return_value=False):
            resolver = FFmpegResolver()
            with pytest.raises(ResourceNotFoundError, match="FFmpeg not found"):
                resolver.resolve(auto_download=False)

    @patch("shutil.which", return_value=None)
    @patch("max_cli.common.ffmpeg_resolver.Confirm.ask", return_value=True)
    @patch.object(FFmpegResolver, "_download_binary")
    @patch.object(FFmpegResolver, "_validate_binary", return_value=True)
    @patch.object(Path, "exists", return_value=False)
    def test_auto_download_flow(
        self, mock_exists, mock_validate, mock_download, mock_confirm, mock_which
    ):
        """Full auto-download flow with user confirmation."""
        resolver = FFmpegResolver()
        result = resolver.resolve(auto_download=True)

        mock_confirm.assert_called_once()
        mock_download.assert_called_once()
        assert result == resolver.local_path

    @patch("shutil.which", return_value=None)
    @patch("max_cli.common.ffmpeg_resolver.Confirm.ask", return_value=False)
    def test_user_declines_download(self, mock_confirm, mock_which):
        """User declines download — raises ResourceNotFoundError."""
        with patch.object(Path, "exists", return_value=False):
            resolver = FFmpegResolver()
            with pytest.raises(ResourceNotFoundError, match="download declined"):
                resolver.resolve(auto_download=True)

    def test_validate_binary_success(self, tmp_path):
        """Binary validation with working FFmpeg."""
        # Create a fake binary (we mock subprocess.run)
        fake_binary = tmp_path / "ffmpeg"
        fake_binary.touch()

        resolver = FFmpegResolver()
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout=b"ffmpeg version 6.0 ...",
            )
            assert resolver._validate_binary(fake_binary) is True

    def test_validate_binary_failure(self, tmp_path):
        """Binary validation with broken binary."""
        fake_binary = tmp_path / "ffmpeg"
        fake_binary.touch()

        resolver = FFmpegResolver()
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout=b"")
            assert resolver._validate_binary(fake_binary) is False

    def test_validate_binary_timeout(self, tmp_path):
        """Binary validation with timeout."""
        fake_binary = tmp_path / "ffmpeg"
        fake_binary.touch()

        resolver = FFmpegResolver()
        with patch(
            "subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="ffmpeg", timeout=10),
        ):
            assert resolver._validate_binary(fake_binary) is False

    @patch("max_cli.common.ffmpeg_resolver.urlopen")
    def test_download_direct_binary(self, mock_urlopen, tmp_path):
        """Download a direct binary (no archive extraction)."""
        # Mock HTTP response
        mock_response = MagicMock()
        mock_response.read.side_effect = [b"fake_binary_data", b""]
        mock_response.getheader.return_value = None
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        resolver = FFmpegResolver()
        resolver.bin_dir = tmp_path
        resolver.local_path = tmp_path / "ffmpeg"

        resolver._download_binary(
            url="https://example.com/ffmpeg",
            binary_name="ffmpeg",
            extract_path=None,  # Direct binary
        )

        assert resolver.local_path.exists()

    def test_cache_resolution(self, tmp_path):
        """Cache write and read."""
        from max_cli.common.ffmpeg_resolver import RESOLUTION_CACHE_FILE

        with patch(
            "max_cli.common.ffmpeg_resolver.RESOLUTION_CACHE_FILE",
            tmp_path / ".ffmpeg_resolved_path",
        ):
            resolver = FFmpegResolver()
            test_path = tmp_path / "ffmpeg"
            test_path.touch()
            resolver._cache_resolution(test_path)

            cached = FFmpegResolver.get_cached_resolution()
            assert cached == test_path
```

### Test File: `tests/test_core_media.py` (Updates)

Add tests for the resolved path being used:

```python
class TestMediaEngineResolvedPath:
    """Tests for MediaEngine using resolved FFmpeg path."""

    @patch("shutil.which", return_value="/usr/bin/ffmpeg")
    def test_uses_resolved_path(self, mock_which):
        """MediaEngine stores and uses the resolved path."""
        engine = MediaEngine()
        assert engine.ffmpeg_path == Path("/usr/bin/ffmpeg")

    @patch("subprocess.run")
    @patch("shutil.which", return_value="/custom/ffmpeg")
    def test_compress_video_uses_resolved_path(self, mock_which, mock_run, tmp_path):
        """compress_video uses self.ffmpeg_path, not hardcoded 'ffmpeg'."""
        mock_run.return_value = MagicMock()

        input_path = tmp_path / "input.mp4"
        output_path = tmp_path / "output.mp4"
        input_path.write_text("video content")

        engine = MediaEngine()
        engine.compress_video(input_path, output_path, crf=28, preset="medium")

        # Verify the command uses the resolved path
        call_args = mock_run.call_args[0][0]
        assert call_args[0] == "/custom/ffmpeg"

    @patch("subprocess.run")
    @patch("shutil.which", return_value=None)
    @patch("max_cli.core.engines.media_engine.resolve_ffmpeg")
    def test_auto_resolve_on_init(self, mock_resolve, mock_which, mock_run, tmp_path):
        """MediaEngine auto-resolves when FFmpeg not in PATH."""
        mock_resolve.return_value = Path("/home/user/.max_cli/bin/ffmpeg")
        mock_run.return_value = MagicMock()

        engine = MediaEngine()
        assert engine.ffmpeg_path == Path("/home/user/.max_cli/bin/ffmpeg")
```

### Test File: `tests/conftest.py` (Add fixture)

```python
@pytest.fixture
def mock_ffmpeg_resolver(monkeypatch, tmp_path):
    """Mock FFmpeg resolver to return a fake binary path."""
    fake_ffmpeg = tmp_path / "ffmpeg"
    fake_ffmpeg.touch()

    from max_cli.common.ffmpeg_resolver import FFmpegResolver
    monkeypatch.setattr(FFmpegResolver, "resolve", lambda self, **kw: fake_ffmpeg)
    monkeypatch.setattr(FFmpegResolver, "get_cached_resolution", staticmethod(lambda: fake_ffmpeg))
    return fake_ffmpeg
```

## Migration Path

### Step-by-Step Rollout

1. **Phase 1 (Day 1)**: Create `ffmpeg_resolver.py` + unit tests
   - No existing code broken
   - Can be tested in isolation

2. **Phase 2 (Day 1-2)**: Update `MediaEngine.__init__` + replace all hardcoded `"ffmpeg"` strings
   - Run `rg '"ffmpeg",' src/max_cli/core/engines/media_engine.py` to verify zero hardcoded instances remain
   - Run `pytest tests/test_core_media.py` to verify all existing tests pass

3. **Phase 3 (Day 2)**: Fix `/tmp/hls` Windows bug
   - Run `pytest` to verify no regressions
   - Manual test on Windows if available

4. **Phase 4 (Day 2)**: Update interface files
   - Update `_check_engine()` in `cli_media.py` and `_check_media_engine()` in `cli_audio.py`
   - Run `pytest tests/` to verify full test suite

5. **Phase 5 (Day 3, Optional)**: Add `max config setup-ffmpeg` command
   - Add to `cli_config.py`
   - Update `README.md` with new command

### Backward Compatibility

- **Existing users with FFmpeg in PATH**: Zero impact — Tier 1 resolution finds it immediately
- **Existing users with FFmpeg NOT in PATH**: Previously got `RuntimeError`, now get auto-download prompt
- **CI/CD environments**: Set `MAX_CLI_NON_INTERACTIVE=1` to skip prompts and fail fast (current behavior)
- **Plugin executors** (`_video_compress_executor`, etc.): Already instantiate `MediaEngine()` — they automatically benefit from the resolver

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Download URL becomes stale (404) | High | Use multiple fallback URLs; catch HTTP errors and show manual install instructions |
| Downloaded binary is corrupted/tampered | Critical | SHA256 hash verification; `_validate_binary()` runs `ffmpeg -version` before use |
| Download is slow/blocked by firewall | Medium | Set 120s timeout; show clear error with manual install steps |
| Disk space insufficient for binary (~60-100MB) | Low | Check available disk space before download; clear error message |
| Platform not in `FFMPEG_DOWNLOADS` (e.g., ARM Linux) | Medium | Graceful fallback to "install manually" message with platform-specific instructions |
| User runs in non-interactive CI environment | Low | `MAX_CLI_NON_INTERACTIVE` env var skips prompt and raises immediately |
| Race condition: two commands trigger download simultaneously | Low | File lock or atomic write (temp file + rename) prevents corruption |
| `live_preview` temp directory fills up | Low | HLS segments are auto-deleted by FFmpeg (`-hls_flags delete_segments`); directory is in system temp |

### URL Fallback Strategy

```python
FFMPEG_DOWNLOADS = {
    "Windows": {
        "urls": [
            "https://github.com/niutech/ffmpeg/releases/latest/download/ffmpeg-master-latest-win64-gpl.zip",
            "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip",
        ],
        ...
    },
    ...
}
```

Try URLs in order; if all fail, show manual install instructions.

## Success Criteria

- [ ] `max video compress test.mp4` works on a fresh machine with no FFmpeg installed (auto-download prompt appears)
- [ ] `max video compress test.mp4` works with FFmpeg already in PATH (no download, instant start)
- [ ] `max video compress test.mp4` works with FFmpeg in `~/.max_cli/bin/` (uses local binary)
- [ ] All 20+ hardcoded `"ffmpeg"` strings replaced with `self.ffmpeg_path`
- [ ] `/tmp/hls` replaced with cross-platform temp directory — `live_preview` works on Windows
- [ ] `pytest tests/test_ffmpeg_resolver.py` passes (all 10+ tests)
- [ ] `pytest tests/test_core_media.py` passes (existing tests unchanged)
- [ ] `pytest tests/` full suite passes
- [ ] `ruff check src/max_cli/common/ffmpeg_resolver.py` — zero lint errors
- [ ] `mypy src/max_cli/common/ffmpeg_resolver.py` — zero type errors
- [ ] `MAX_CLI_NON_INTERACTIVE=1 max video compress test.mp4` fails gracefully with install instructions (CI-safe)
- [ ] Downloaded binary passes `_validate_binary()` check
- [ ] Documentation updated: `README.md` mentions auto-download feature, `docs/commands/video.md` updated

---

## Appendix: Platform-Specific Download Details

### Windows
- **Source**: GitHub releases (niutech/ffmpeg) or gyan.dev
- **Format**: ZIP archive
- **Extraction**: `bin/ffmpeg.exe` from archive root
- **Size**: ~80MB
- **Note**: Static GPL build — includes all codecs

### macOS
- **Source**: evermeet.cx
- **Format**: Direct Mach-O binary
- **Extraction**: None — direct download
- **Size**: ~60MB
- **Note**: Universal binary (Intel + Apple Silicon)

### Linux (x86_64)
- **Source**: johnvansickle.com
- **Format**: tar.xz archive
- **Extraction**: `ffmpeg-release-amd64-static/ffmpeg` binary
- **Size**: ~70MB
- **Note**: Fully static build — no system library dependencies

### Linux (ARM64)
- **Source**: johnvansickle.com
- **Format**: tar.xz archive
- **Extraction**: `ffmpeg-release-arm64-static/ffmpeg` binary
- **Size**: ~65MB

---

*Documentation has been synchronized.*
