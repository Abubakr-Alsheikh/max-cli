# Video Commands

The `max video` group wraps FFmpeg. Most commands take one input file and accept `-o` to set the output path. Without `-o`, Max writes a new file next to the input and leaves the original alone.

## FFmpeg Auto-Resolution

Max finds FFmpeg in three steps:

1. Check the system PATH (`shutil.which`)
2. Check `~/.max_cli/bin/` for a binary it downloaded before
3. Offer to download a binary for your platform

You don't need to install FFmpeg yourself. To install it ahead of time, run:

```bash
max config setup-ffmpeg
```

## compress

Compress a video to H.264 MP4.

```bash
max video compress TARGET [-o OUTPUT] [--level LEVEL] [--queue]
```

**Options:**

- `-o` - Output path
- `--level` - `high` (CRF 23), `balanced` (CRF 28) or `max` (CRF 35, smallest file). Default: `balanced`
- `--queue`, `-q` - Add the job to the background queue instead of running it now. See [Queue](queue.md).

**Examples:**

```bash
max video compress movie.mp4
max video compress movie.mp4 --level high
max video compress movie.mp4 --level max -o small.mp4
max video compress movie.mp4 --queue
```

## convert

Change the video container, for example MKV to MP4.

```bash
max video convert TARGET [--format FORMAT]
```

**Options:**

- `--format`, `-f` - Target format: `mp4`, `mkv` or `avi` (default: `mp4`)

## to-audio

Extract the audio track from a video.

```bash
max video to-audio TARGET [--format FORMAT] [--quality QUALITY] [--output OUTPUT]
```

**Options:**

- `--format`, `-f` - `mp3`, `wav`, `flac` or `aac` (default: `mp3`)
- `--quality`, `-q` - `s` (96k), `m` (128k), `h` (192k) or `x` (320k). Default: `h`
- `--output`, `-o` - Output path

**Examples:**

```bash
max video to-audio lecture.mp4
max video to-audio lecture.mp4 --format wav
max video to-audio lecture.mp4 -q x
```

## cut

Trim a video. `--start` is required. Pass `--end` or `--duration`, or neither to keep everything up to the end of the file.

```bash
max video cut TARGET --start TIME [--end TIME | --duration SECONDS] [-o OUTPUT]
```

**Options:**

- `--start`, `-s` - Start time, such as `00:01:00` or `60` (required)
- `--end`, `-e` - End time
- `--duration`, `-d` - Length to keep, such as `10`
- `-o` - Output file

**Examples:**

```bash
max video cut movie.mp4 --start 0:30 --end 1:00
max video cut movie.mp4 --start 0 --duration 30
```

## concat

Join several videos into one.

```bash
max video concat TARGET [-o OUTPUT] [--method METHOD]
```

`TARGET` is a glob pattern such as `"*.mp4"`, or a text file with one `file /path/to/video.mp4` line per video.

**Options:**

- `-o` - Output file
- `--method`, `-m` - `fast` copies the streams without re-encoding. Use it when every input has the same codec and size. `safe` re-encodes and scales every clip to 1920x1080, so it works with mixed inputs. Default: `fast`

**Examples:**

```bash
max video concat "*.mp4" -o joined.mp4
max video concat list.txt --method safe
```

## gif

Turn a video clip into a GIF.

```bash
max video gif TARGET [-o OUTPUT] [--width PX] [--fps FPS]
```

**Options:**

- `-o` - Output GIF
- `--width` - Width in pixels; height scales to match (default: 480)
- `--fps` - Frames per second (default: 15)

## snap

Save a JPG screenshot at a timestamp.

```bash
max video snap TARGET [--time TIME] [-o OUTPUT]
```

**Options:**

- `--time`, `-t` - Timestamp (default: `00:00:05`)
- `-o` - Output image

## louder

Raise the volume of a quiet recording.

```bash
max video louder TARGET [--db DECIBELS] [-o OUTPUT]
```

**Options:**

- `--db` - Decibels to add (default: 5.0)
- `-o` - Output file

## mute

Remove the audio track.

```bash
max video mute TARGET [-o OUTPUT]
```

## brightness

Adjust brightness and contrast.

```bash
max video brightness TARGET [--brightness VALUE] [--contrast VALUE] [-o OUTPUT]
```

**Options:**

- `--brightness`, `-b` - 0.0 to 2.0, where 1.0 is unchanged (default: 1.0)
- `--contrast`, `-c` - 0.0 to 2.0, where 1.0 is unchanged (default: 1.0)
- `-o` - Output file

## color

Apply a color grading preset.

```bash
max video color TARGET [--preset PRESET] [-o OUTPUT]
```

**Presets:** `vivid` (default), `vintage`, `noir`, `warm`, `cool`, `fade`

## stabilize

Smooth out shaky footage.

```bash
max video stabilize TARGET [-o OUTPUT]
```

## normalize

Set the audio loudness to a target level.

```bash
max video normalize TARGET [--level LUFS] [-o OUTPUT]
```

**Options:**

- `--level`, `-l` - Target loudness in LUFS (default: -20.0)
- `-o` - Output file

## denoise

Remove background noise such as hiss, hum, fans or room noise.

```bash
max video denoise TARGET [OPTIONS]
```

**Options:**

- `--mode`, `-m` - `auto` (general), `hiss` (constant hiss), `hum` (low rumble) or `speech` (RNNoise, best for voice). Default: `auto`
- `--strength`, `-s` - `mild`, `medium` or `aggressive`. Applies to `auto` mode only. Default: `medium`
- `--output`, `-o` - Output file (default: `{stem}_denoised{ext}`)
- `--queue`, `-q` - Add the job to the background queue

**Examples:**

```bash
# Auto mode, medium strength
max video denoise recording.mp4

# Remove constant microphone hiss
max video denoise podcast.mp4 --mode hiss

# Cut low-frequency rumble (AC, traffic)
max video denoise lecture.mp4 --mode hum

# Best for speech and podcasts
max video denoise recording.mp4 --mode speech

# Very noisy audio
max video denoise noisy.mp4 --strength aggressive

# Run it later from the queue
max video denoise long_clip.mp4 --queue
```

> **Note**: `auto` mode uses FFmpeg's `anlmdn` filter, which is CPU-heavy. For faster results, try `--mode hiss` or `--mode hum`. Max copies the video stream (`-c:v copy`) and re-encodes only the audio.

## audio-convert

Convert audio between formats, for example WAV to MP3.

```bash
max video audio-convert TARGET [--format FORMAT] [--quality QUALITY] [-o OUTPUT]
```

**Options:**

- `--format`, `-f` - `mp3`, `aac`, `flac`, `wav` or `ogg` (default: `mp3`)
- `--quality`, `-q` - `s` (128k), `m` (192k) or `h` (320k). Default: `h`
- `-o` - Output file

## record

Record your screen. Press `Ctrl+C` to stop when you don't set a duration.

```bash
max video record [OUTPUT] [--duration SECONDS] [--fps FPS] [--audio]
```

**Options:**

- `OUTPUT` - Output file (default: `screen recording.mp4`)
- `--duration`, `-d` - Recording length in seconds
- `--fps` - Frames per second (default: 30)
- `--audio`, `-a` - Include system audio

## stream

Stream a video file to an RTMP server such as Twitch or YouTube.

```bash
max video stream TARGET --url RTMP_URL [--bitrate RATE] [--preset PRESET]
```

**Options:**

- `--url`, `-u` - RTMP server URL (required)
- `--bitrate`, `-b` - Video bitrate (default: `4500k`)
- `--preset`, `-p` - Encoder preset from `ultrafast` to `slow` (default: `veryfast`)

**Example:**

```bash
max video stream video.mp4 -u rtmp://live.twitch.tv/app -b 6000k
```

## preview

Serve a video over HTTP as an HLS stream. Open `http://localhost:8080/live.m3u8` in a media player to watch.

```bash
max video preview TARGET [--port PORT] [--bitrate RATE]
```

**Options:**

- `--port`, `-p` - HTTP port (default: 8080)
- `--bitrate`, `-b` - Transcoding bitrate (default: `2000k`)
