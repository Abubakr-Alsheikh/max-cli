# Plan: Audio Noise Removal for Video (`max video denoise`)

> Status: Draft
> Priority: P1 (Quality-of-life improvement)
> Depends on: FFmpeg (anlmdn/afftdn filters — built into FFmpeg >= 4.4)

## Overview

Add a `max video denoise` command that removes background noise (hiss, hum, fan, ambient room noise) from a video's audio track. The user gets a cleaner audio track without needing Audacity or a separate audio editor. The command works on video files (replaces audio track) and optionally on standalone audio files.

## Goals

- [ ] **New `denoise` command** under `max video` (and `max audio`) to reduce/remove background noise.
- [ ] **Three noise reduction modes**: `auto` (default — `anlmdn`), `hiss` (`afftdn` for constant background hiss), `hum` (`highpass` filter for low-frequency rumble).
- [ ] **Strength parameter** for `auto` mode (mild/medium/aggressive).
- [ ] **Profile learning** — optional `--profile` flag to learn noise profile from a silent section of the video, then apply that profile for more targeted removal.
- [ ] **Drop-in output** — defaults to `input_stem_denoised.mp4`; `--output` to customize.
- [ ] **Queue support** — follow existing `--queue` pattern for long-running denoising jobs.
- [ ] **Tests** — unit tests for each noise removal method, mocking `subprocess.run`.

## Files to Modify

| # | File | Change |
|---|------|--------|
| 1 | `src/max_cli/core/engines/media_engine.py` | Add `denoise_audio()` method |
| 2 | `src/max_cli/interface/cli_media.py` | Add `denoise` Typer command |
| 3 | `src/max_cli/interface/cli_audio.py` | Add `denoise` Typer command (call `_get_media_engine()`) |
| 4 | `src/max_cli/core/engines/task_queue.py` | Add `VIDEO_DENOISE` / `AUDIO_DENOISE` to `TaskType` enum |
| 5 | `src/max_cli/core/engines/media_engine.py` | Add `_video_denoise_executor` and `_audio_denoise_executor` + register them |
| 6 | `tests/test_core_media.py` | Add `TestMediaEngineDenoise` class |

## Implementation Specification

### 1. Core Engine — `media_engine.py` (lines ~739-806)

Add AFTER `screen_record()` method, BEFORE the module-level executors.

#### Method Signature

```python
def denoise_audio(
    self,
    input_path: Path,
    output_path: Path,
    mode: str = "auto",
    strength: str = "medium",
    profile: Optional[str] = None,
) -> Dict[str, Any]:
```

#### Parameters

| Param | Type | Default | Options | Description |
|-------|------|---------|---------|-------------|
| `input_path` | `Path` | required | — | Input video or audio file |
| `output_path` | `Path` | required | — | Output file path |
| `mode` | `str` | `"auto"` | `"auto"`, `"hiss"`, `"hum"` | Denoising algorithm |
| `strength` | `str` | `"medium"` | `"mild"`, `"medium"`, `"aggressive"` | Only used in `auto` mode |
| `profile` | `Optional[str]` | `None` | — | Path to noise profile file (learned via `--learn` or external tool); `hiss` and `hum` modes ignore this |

#### Return Value

Standard engine dict:
```python
{
    "output_path": str(output_path),
    "output_files": [str(output_path)],
    "message": f"Denoised: {input_path.name} (mode={mode})",
}
```

#### FFmpeg Commands by Mode

**Mode: `auto`** (default) — uses `anlmdn` filter

FFmpeg >= 4.4 has the `anlmdn` (Audio Non-Local Means DeNoising) filter. It's a smart algorithm that works well on general background noise without needing a profile.

Strength mapping:

| Strength | `anlmdn` params | Effect |
|----------|-----------------|--------|
| `mild` | `0.0001:0.016:0.016` | Light touch — preserves subtle audio detail |
| `medium` | `0.0005:0.016:0.016` | Balanced — good for moderate fan/ambient noise |
| `aggressive` | `0.003:0.016:0.016` | Heavy — use when noise is loud (may introduce artifacts) |

→ `anlmdn` filter syntax: `anlmdn=s=<strength>:p=<patch_duration_sec>:o=<research_duration_sec>`

> **Important**: `p` (patch duration) and `o` (research duration) are in **seconds** (float), valid range `p=[0.001, 0.1]` and `o=[0.001, 1.0]`. Only `s` (strength) should be tuned for aggressiveness — patch/research at defaults (0.016) works universally.

```python
# Mode: auto
denoise_strength_map = {
    "mild": "0.0001:0.016:0.016",
    "medium": "0.0005:0.016:0.016",
    "aggressive": "0.003:0.016:0.016",
}
anlmdn_params = denoise_strength_map.get(strength, "0.0005:0.016:0.016")

if profile:  # Use profile with anlmdn if provided (future-proofing)
    pass  # anlmdn doesn't natively use profiles, but we leave the param for extensibility

cmd = [
    str(self.ffmpeg_path),
    "-y",
    "-i",
    str(input_path),
    "-af",
    f"anlmdn=s={anlmdn_params}",
    "-c:v",
    "copy",  # Copy video stream without re-encoding (fast!)
    "-loglevel",
    "error",
    str(output_path),
]
```

**Important**: Video stream is copied (`-c:v copy`) so it's fast. Only the audio is re-encoded.

**Mode: `hiss`** — uses `afftdn` filter

For constant background hiss (e.g., microphone hiss, tape hiss). The `afftdn` filter uses FFT-based noise reduction.

> **Note on defaults**: `nr=12` (noise reduction in dB) and `nf=-40` (noise floor in dBFS) are conservative — they suppress hiss without pumping artifacts. Overly aggressive values (e.g., `nr=20:nf=-25`) can cause audible "watery" artifacts on quiet audio. These defaults work well for the most common case (microphone hiss).

```python
# Mode: hiss
cmd = [
    str(self.ffmpeg_path),
    "-y",
    "-i",
    str(input_path),
    "-af",
    "afftdn=nr=12:nf=-40",
    "-c:v",
    "copy",
    "-loglevel",
    "error",
    str(output_path),
]
```

If `profile` is provided in hiss mode, it's silently ignored for MVP — future enhancement could pass `nt=<noise_type>` to `afftdn`.

**Mode: `hum`** — uses `highpass` filter only

For low-frequency hum (50/60 Hz electrical hum, AC, refrigerator, traffic rumble). A highpass filter at 80 Hz cleanly cuts sub-bass rumble without affecting voices or music.

```python
# Mode: hum
# Highpass at 80 Hz to cut low rumble (AC, traffic, electrical hum)
cmd = [
    str(self.ffmpeg_path),
    "-y",
    "-i",
    str(input_path),
    "-af",
    "highpass=f=80",
    "-c:v",
    "copy",
    "-loglevel",
    "error",
    str(output_path),
]
```

The `hum_cutoff` parameter (default 80 Hz) is exposed in the engine method for fine-tuning, but not exposed in the MVP CLI. If power users need it, add `--cutoff` in a follow-up.

```python
cutoff: Optional[int] = None,  # Only used in 'hum' mode; default 80 Hz
```

#### Complete Method Implementation

The full method (wrapped logic):

1. Validate `input_path.is_file()` — raise `FileNotFoundError` if missing.
2. Validate `mode` is one of `"auto"`, `"hiss"`, `"hum"` — raise `ValueError` if not.
3. Validate `strength` is one of `"mild"`, `"medium"`, `"aggressive"` — only in `auto` mode.
4. Warn if `profile` is provided but mode doesn't support it (log a debug/info message via `console.print` or just silently ignore — for MVP, silently ignore is acceptable since the param exists for future extensibility).
5. Build the FFmpeg command based on mode.
6. Call `self._run(cmd)`.
7. Return the standard result dict.

```python
def denoise_audio(
    self,
    input_path: Path,
    output_path: Path,
    mode: str = "auto",
    strength: str = "medium",
    profile: Optional[str] = None,
    hum_cutoff: int = 80,
) -> Dict[str, Any]:
    if not input_path.is_file():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    valid_modes = {"auto", "hiss", "hum"}
    if mode not in valid_modes:
        raise ValueError(f"Unknown denoise mode: {mode}. Use: {', '.join(sorted(valid_modes))}")

    if mode == "auto":
        valid_strengths = {"mild", "medium", "aggressive"}
        if strength not in valid_strengths:
            raise ValueError(f"Unknown strength: {strength}. Use: {', '.join(sorted(valid_strengths))}")

        strength_map = {
            "mild": "0.0001:0.016:0.016",
            "medium": "0.0005:0.016:0.016",
            "aggressive": "0.003:0.016:0.016",
        }
        params = strength_map[strength]
        af_filter = f"anlmdn=s={params}"

    elif mode == "hiss":
        af_filter = "afftdn=nr=12:nf=-40"

    elif mode == "hum":
        af_filter = f"highpass=f={hum_cutoff}"

    cmd = [
        str(self.ffmpeg_path),
        "-y",
        "-i",
        str(input_path),
        "-af",
        af_filter,
        "-c:v",
        "copy",
        "-loglevel",
        "error",
        str(output_path),
    ]
    self._run(cmd)
    return {
        "output_path": str(output_path),
        "output_files": [str(output_path)],
        "message": f"Denoised: {input_path.name} (mode={mode})",
    }
```

### 2. CLI Interface — `cli_media.py` (after `mute` command ~line 301, or after `normalize` command ~line 470)

Add the Typer command. Follow the exact same pattern as `normalize` or `mute`.

#### Typer Command Definition

```python
@app.command("denoise")
@app.command("dn", hidden=True)
def denoise_audio_cmd(
    target: Path = typer.Argument(..., help="Video or audio file with background noise."),
    mode: str = typer.Option(
        "auto",
        "--mode",
        "-m",
        help="Denoise mode: auto (general), hiss (constant hiss), hum (low rumble).",
    ),
    strength: str = typer.Option(
        "medium",
        "--strength",
        "-s",
        help="Denoising strength: mild, medium, aggressive (auto mode only).",
    ),
    output: Optional[Path] = typer.Option(None, "-o", "--output", help="Output file."),
    queue: bool = typer.Option(False, "--queue", "-q", help="Add to background queue."),
):
    """
    Remove background noise from audio/video.

    Uses AI-powered filtering to clean up hiss, hum, fan noise, and ambient sounds.
    The --strength parameter only applies to 'auto' mode.

    Examples:
      max video denoise recording.mp4
      max video denoise podcast.mp4 --mode hiss --strength aggressive
      max video denoise lecture.mp4 --mode hum --output clean_lecture.mp4
    """
    _get_engine()

    # Resolve output path
    if not output:
        ext = target.suffix
        # Note: target.suffix returns the last extension only (e.g., ".mp4").
        # For compound extensions like ".tar.gz", use target.suffixes[0] instead.
        # This doesn't apply to video/audio files in practice.
        output = target.parent / f"{target.stem}_denoised{ext}"

    # CLI-side validation: strength only meaningful for auto mode
    if mode != "auto":
        valid_strength_modes = {"mild", "medium", "aggressive"}
        if strength in valid_strength_modes:
            strength = "medium"

    # Build payload for queue (if applicable)
    if queue:
        from max_cli.core.engines.daemon_manager import DaemonManager
        from max_cli.core.engines.task_queue import TaskItem, TaskType

        dm = DaemonManager()
        task = TaskItem(
            type=TaskType.VIDEO_DENOISE,
            title=f"Denoise {target.name}",
            description=f"mode={mode}, strength={strength}",
            payload={
                "input_path": str(target),
                "output_path": str(output),
                "mode": mode,
                "strength": strength,
            },
        )
        dm.add(task)
        console.print(f"[green]Queued:[/green] {target.name} (ID: {task.id})")
        console.print("[dim]Run 'max queue status' to monitor.[/dim]")
        return

    console.print(f"[cyan]Denoising audio (mode: {mode}, strength: {strength})...[/cyan]")

    with console.status("[bold green]Removing background noise...[/bold green]"):
        try:
            eng = _get_engine()
            result = eng.denoise_audio(target, output, mode=mode, strength=strength)

            final_size = output.stat().st_size
            log_success(f"Denoised audio saved: {output.name}")
            console.print(f"File Size: [green]{format_size(final_size)}[/green]")

        except Exception as e:
            log_error(f"Denoising failed: {e}")
```

### 3. CLI Interface — `cli_audio.py`

Add the same `denoise` command to the audio CLI, calling `_get_media_engine()` instead (same pattern as `compress` command in `cli_audio.py` at ~line 70). This allows `max audio denoise` too.

For `cli_audio.py`:
- Import `format_size` is already there
- Use `_get_media_engine()` helper  
- No `--queue` flag for audio CLI (to keep it minimal — video gets it for long jobs)
- Rest is identical logic

### 4. Task Queue — `task_queue.py`

Add two new values to the `TaskType` enum (line ~30):

```python
VIDEO_DENOISE = "video_denoise"
AUDIO_DENOISE = "audio_denoise"
```

Insert after `VIDEO_TO_AUDIO` (line 23).

### 5. Queue Executors — `media_engine.py` (bottom of file)

Add two new executor functions after the existing executors:

```python
def _video_denoise_executor(task: TaskItem) -> Dict[str, Any]:
    engine = MediaEngine()
    payload = task.payload
    input_path = Path(payload["input_path"])
    output_path = Path(
        payload.get("output_path", input_path.parent / f"{input_path.stem}_denoised{input_path.suffix}")
    )
    engine.denoise_audio(
        input_path=input_path,
        output_path=output_path,
        mode=payload.get("mode", "auto"),
        strength=payload.get("strength", "medium"),
        hum_cutoff=payload.get("hum_cutoff", 80),
    )
    return {
        "output_path": str(output_path),
        "output_files": [str(output_path)],
    }
```

Register at the bottom:
```python
register_executor(TaskType.VIDEO_DENOISE, _video_denoise_executor)
register_executor(TaskType.AUDIO_DENOISE, _video_denoise_executor)  # Same logic works for audio-only
```

### 6. Tests — `tests/test_core_media.py`

Add a new test class `TestMediaEngineDenoise` after the existing classes.

Test cases:

| # | Test | What it checks |
|---|------|----------------|
| 1 | `test_denoise_auto_default` | Default mode calls `subprocess.run` with `anlmdn` filter and `-c:v copy` |
| 2 | `test_denoise_hiss_mode` | `hiss` mode uses `afftdn` filter |
| 3 | `test_denoise_hum_mode` | `hum` mode uses `highpass` filter |
| 4 | `test_denoise_auto_strength_mild` | Mild strength maps to correct params |
| 5 | `test_denoise_auto_strength_aggressive` | Aggressive strength maps to correct params |
| 6 | `test_denoise_invalid_mode` | Raises `ValueError` on invalid mode |
| 7 | `test_denoise_invalid_strength` | Raises `ValueError` on invalid strength |
| 8 | `test_denoise_input_not_found` | Missing input file raises `FileNotFoundError` |
| 9 | `test_denoise_output_path` | Output file path dict matches input |
| 10 | `test_denoise_ffmpeg_error` | FFmpeg failure raises `RuntimeError` with message |

Test pattern (follow existing style at line 128-140):

```python
class TestMediaEngineDenoise:
    @patch("subprocess.run")
    @patch("shutil.which")
    def test_denoise_auto_default(self, mock_which, mock_run, tmp_path):
        mock_which.return_value = "/usr/bin/ffmpeg"
        mock_run.return_value = MagicMock()

        input_path = tmp_path / "input.mp4"
        output_path = tmp_path / "output.mp4"
        input_path.write_text("video content")

        engine = MediaEngine()
        engine.denoise_audio(input_path, output_path)

        mock_run.assert_called_once()
        call_args = mock_run.call_args[0][0]
        assert call_args[0] == "/usr/bin/ffmpeg"
        assert "-af" in call_args
        af_index = call_args.index("-af")
        assert "anlmdn" in call_args[af_index + 1]
        assert "-c:v" in call_args
        assert call_args[call_args.index("-c:v") + 1] == "copy"
        assert call_args[-1] == str(output_path)

    @patch("subprocess.run")
    @patch("shutil.which")
    def test_denoise_hiss_mode(self, mock_which, mock_run, tmp_path):
        # Similar pattern, assert "afftdn" in the -af arg
        ...

    @patch("subprocess.run")
    @patch("shutil.which")
    def test_denoise_hum_mode(self, mock_which, mock_run, tmp_path):
        # Similar pattern, assert "highpass" in the -af arg
        ...

    @patch("subprocess.run")
    @patch("shutil.which")
    def test_denoise_ffmpeg_error(self, mock_which, mock_run, tmp_path):
        import subprocess
        mock_which.return_value = "/usr/bin/ffmpeg"
        mock_run.side_effect = subprocess.CalledProcessError(1, "ffmpeg", stderr=b"Noise reduction failed")

        input_path = tmp_path / "input.mp4"
        output_path = tmp_path / "output.mp4"
        input_path.write_text("video content")

        engine = MediaEngine()
        with pytest.raises(RuntimeError, match="FFmpeg Error"):
            engine.denoise_audio(input_path, output_path)

    def test_denoise_invalid_mode(self, tmp_path):
        with patch("shutil.which", return_value="/usr/bin/ffmpeg"):
            engine = MediaEngine()
            input_path = tmp_path / "input.mp4"
            output_path = tmp_path / "output.mp4"
            input_path.write_text("video content")

            with pytest.raises(ValueError, match="Unknown denoise mode"):
                engine.denoise_audio(input_path, output_path, mode="invalid")

    def test_denoise_invalid_strength(self, tmp_path):
        with patch("shutil.which", return_value="/usr/bin/ffmpeg"):
            engine = MediaEngine()
            input_path = tmp_path / "input.mp4"
            output_path = tmp_path / "output.mp4"
            input_path.write_text("video content")

            with pytest.raises(ValueError, match="Unknown strength"):
                engine.denoise_audio(input_path, output_path, strength="invalid")

    def test_denoise_input_not_found(self, tmp_path):
        with patch("shutil.which", return_value="/usr/bin/ffmpeg"):
            engine = MediaEngine()
            input_path = tmp_path / "nonexistent.mp4"
            output_path = tmp_path / "output.mp4"

            with pytest.raises(FileNotFoundError, match="Input file not found"):
                engine.denoise_audio(input_path, output_path)
```

### 7. Integration / CLI Tests (Optional Enhancement)

For the CLI layer, add a test file `tests/test_cli_media.py` or add to the existing one if it exists:

Check `tests/` directory — if there's no existing CLI test file for media, this is optional for MVP but recommended.

```python
from typer.testing import CliRunner
from max_cli.main import app

runner = CliRunner()

def test_denoise_command_help():
    result = runner.invoke(app, ["video", "denoise", "--help"])
    assert result.exit_code == 0
    assert "Denoise" in result.stdout or "noise" in result.stdout.lower()
```

## Risks & Mitigations

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| FFmpeg version < 4.4 missing `anlmdn` | Medium | Check with `ffmpeg -filters 2>/dev/null | grep anlmdn` before running; fallback to `afftdn` which is older. Add a version check or filter test in `_run()`. Actually — just let FFmpeg fail naturally; the error message will be caught by `_run()` → `RuntimeError("FFmpeg Error: ...")` and shown to user. |
| `hum` mode highpass cuts too much bass | Low | Default 80 Hz is safe for most content (voice, music). User can adjust via `--cutoff` if added. For MVP, 80 Hz is a sensible default. |
| Aggressive denoising degrades audio quality | Low | Users opt into strength explicitly. The aggressive mapping is conservative; real artifacts only appear if audio is heavily compressed. |
| Video re-encode removes quality | None | `-c:v copy` means video stream is NOT re-encoded. Only audio is processed. Video quality is preserved 100%. |
| Large files take long to process | Medium | `--queue` flag offloads to background daemon. User can continue using CLI. |

## Verification Checklist

- [ ] `max video denoise video.mp4` produces `video_denoised.mp4` with cleaner audio and same video quality
- [ ] `max video denoise video.mp4 --mode hiss` uses `afftdn` filter (verify via FFmpeg command analysis)
- [ ] `max video denoise video.mp4 --mode hum` uses `highpass` filter
- [ ] `max video denoise video.mp4 --strength mild` has lighter denoising effect
- [ ] `max video denoise video.mp4 --strength aggressive` has stronger denoising effect
- [ ] Invalid `--mode` shows clear error message, not stacktrace
- [ ] Invalid `--strength` shows clear error message, not stacktrace
- [ ] `max video denoise video.mp4 -o custom.mp4` writes to `custom.mp4`
- [ ] `max video denoise video.mp4 --queue` adds task to queue (verify with `max queue status`)
- [ ] `max audio denoise audio.mp3` also works
- [ ] `pytest tests/test_core_media.py -k "Denoise"` passes all tests
- [ ] `ruff check src/max_cli/core/engines/media_engine.py src/max_cli/interface/cli_media.py src/max_cli/interface/cli_audio.py` passes cleanly
- [ ] `mypy src/max_cli/core/engines/media_engine.py src/max_cli/interface/cli_media.py src/max_cli/interface/cli_audio.py` passes cleanly
- [ ] `max --help` starts in under 200ms (no new module-level heavy imports)
- [ ] Lazy loading preserved: all heavy imports remain inside methods, engines created via `_get_engine()`

## Future Enhancements (Out of Scope for MVP)

- **Profile-based denoising**: Use a sample of pure noise (e.g., first 2 seconds of silence) to build a noise profile, then apply that profile via `afftdn=nr=20:nf=-25:nt=w`. Could add `--learn` flag.
- **`arnndn` model-based denoising**: FFmpeg supports RNN-based denoising via `arnndn` filter, but it requires a separate `.rrn` model file. Could be added as a future mode.
- **Multi-channel support**: `anlmdn` works on each channel independently. Test with 5.1 audio.
- **Preview**: Add a `--dry-run` flag that shows the FFmpeg command without running it, for debugging.
- **Progress bar**: For long denoising jobs, can add FFmpeg progress parsing (like `-progress pipe:1`).

## Estimated Effort

- Core engine method: ~40 lines
- CLI command (video): ~55 lines
- CLI command (audio): ~40 lines
- Task queue types: 2 lines
- Executors: ~25 lines
- Tests: ~120 lines
- **Total: ~280 lines**

Expected implementation time for an experienced Python developer: 1–2 hours (including testing).

---

## Appendix: Code Review Findings (Applied)

The above spec has been revised based on a code review of the initial draft. Below is a summary of every issue found and its resolution:

| # | Issue | Severity | Resolution |
|---|-------|----------|------------|
| 1 | `anlmdn` patch duration `p` and research size `o` were integer (e.g., `7:11`) but FFmpeg expects float **seconds** — `p=10` crashed with `out of range [0.001 - 0.1]` | 🔴 **Critical (runtime crash)** | Changed to default 0.016s: `"0.0001:0.016:0.016"`, `"0.0005:0.016:0.016"`, `"0.003:0.016:0.016"`. Only strength `s` is varied; patch/research kept at defaults. |
| 2 | `hum` mode description mentioned `lowpass=f=8000` but final code only used `highpass` | 🟡 Minor | Clarified `hum` uses `highpass` only; removed misleading lowpass reference |
| 3 | No input file existence check | 🟡 Minor | Added `FileNotFoundError` guard at top of `denoise_audio()` |
| 4 | `profile` parameter silently ignored | 🟡 Minor | Documented as future-extensible; no runtime action needed for MVP |
| 5 | `afftdn` defaults too aggressive (`nr=20:nf=-25`) causing artifacts | 🟡 Medium | Changed to `nr=12:nf=-40` (conservative, artifact-free) |
| 6 | Output suffix ignores compound extensions (`.tar.gz`) | 🟢 Info | Noted as non-issue for video/audio; added inline comment |
| 7 | Queue executor omits `hum_cutoff` | 🟡 Minor | Added `hum_cutoff=payload.get("hum_cutoff", 80)` to executor |
| 8 | `--strength` accepted but silently ignored in non-`auto` modes | 🟡 Minor | Added CLI-side fallback: resets strength to `"medium"` for non-auto modes |
| 9 | Test suite missing `test_denoise_input_not_found` | 🟢 Info | Added `FileNotFoundError` test case |
