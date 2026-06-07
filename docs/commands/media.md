# Media Commands

## FFmpeg Auto-Resolution

Max automatically resolves FFmpeg using a 3-tier strategy:
1. Check system PATH (`shutil.which`)
2. Check `~/.max_cli/bin/` for previously downloaded binary
3. Auto-download platform-specific binary with user confirmation

No manual FFmpeg installation is required. To manually install:

```bash
max config setup-ffmpeg
```

## compress

Compress video files.

```bash
max media compress <input> [-q QUALITY] [-o OUTPUT]
```

## extract-audio

Extract audio from video.

```bash
max media extract-audio <input> [-o OUTPUT]
```

## convert

Convert video format.

```bash
max media convert <input> <output_format> [-o OUTPUT]
```

## trim

Trim video to specified duration.

```bash
max media trim <input> --start <seconds> --end <seconds> [-o OUTPUT]
```

## concat

Concatenate multiple videos.

```bash
max media concat "*.mp4" [-o OUTPUT]
```

## video-to-gif

Convert video to animated GIF.

```bash
max media video-to-gif <input> [-o OUTPUT]
```

## denoise

Remove background noise from video/audio (hiss, hum, fan, ambient room noise).

```bash
max video denoise <input> [OPTIONS]
```

**Options:**
- `--mode`, `-m` - Denoise mode: `auto` (general), `hiss` (constant hiss), `hum` (low rumble), `speech` (RNNoise, best for voice) (default: `auto`)
- `--strength`, `-s` - Denoising strength: `mild`, `medium`, `aggressive` (auto mode only, default: `medium`)
- `--output`, `-o` - Output file (default: `{stem}_denoised{ext}`)
- `--queue`, `-q` - Add to background queue

**Examples:**
```bash
# Auto-denoise (anlmdn filter, medium strength)
max video denoise recording.mp4

# Remove constant microphone hiss
max video denoise podcast.mp4 --mode hiss

# Cut low-frequency rumble (AC, traffic)
max video denoise lecture.mp4 --mode hum

# BEST for speech/podcasts (RNNoise neural network)
max video denoise recording.mp4 --mode speech

# Aggressive denoising for very noisy audio
max video denoise noisy.mp4 --strength aggressive

# Process in background queue
max video denoise long_clip.mp4 --queue
```

> **Note**: `auto` mode uses FFmpeg's `anlmdn` filter (CPU-heavy). For faster results, try `--mode hiss` or `--mode hum`. Video stream is copied (`-c:v copy`), only audio is re-encoded.

## brightness

Adjust video brightness.

```bash
max media brightness <input> --value <0-2> [-o OUTPUT]
```

## color

Apply color preset to video.

```bash
max media color <input> --preset <preset> [-o OUTPUT]
```

**Presets:** vivid, vintage, noir, warm, cool, fade
