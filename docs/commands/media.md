# Video Commands

The `max video` group wraps FFmpeg. Most commands take an input file and accept `-o` to set the output path. Without `-o`, Max writes a new file next to the input and leaves the original alone. Each command below names its default result, where `{stem}` is the input's name without its extension.

## FFmpeg Auto-Resolution

Max finds FFmpeg in three steps:

1. Check the system PATH (`shutil.which`)
2. Check `~/.max_cli/bin/` for a binary it downloaded before
3. Offer to download a binary for your platform

You don't need to install FFmpeg yourself. To install it ahead of time, run:

```bash
max config setup-ffmpeg
```

## Several files at once

Every command below except `concat`, `record`, `stream` and `preview` takes several files, a folder or a pattern as well as one file:

```bash
max video compress a.mp4 b.mp4            # these two files
max video compress ~/Videos --recursive   # every video in the folder and its subfolders
max video audio-convert "*.m4a" --queue   # every M4A here, as background jobs
```

- A folder gives you its video files. `cut`, `louder`, `normalize`, `denoise` and `audio-convert` take its audio files too. Max leaves out hidden files and folders.
- Quote a pattern (`"*.m4a"`) so Max expands it, not your shell.
- `--recursive` looks in subfolders too.
- With a folder or a pattern, Max skips a file whose result already exists (`a.mp4` when `a_compressed.mp4` is there) and doesn't treat its own earlier results as new input. `--redo` runs those files again. Files you name one by one always run. `cut` skips nothing, so it has no `--redo`.
- Max runs up to four files at a time and ticks off each one as it finishes. When a file fails, the others still run; Max lists the failures at the end and exits with code 1.
- `-o` names one file, so Max refuses it with several. Each result goes next to its file.
- `--queue` (every command here except `snap`) adds one job per file to the background queue and starts a background worker. The worker keeps going after you close the terminal. Run `max queue status` to watch it. See [Queue](queue.md). `compress` and `denoise` also take `-q` for `--queue`; in `to-audio` and `audio-convert`, `-q` means `--quality`.

## compress

Compress a video to H.264 MP4.

```bash
max video compress TARGET... [-o OUTPUT] [--level LEVEL] [--queue]
```

**Options:**

- `-o` - Output path (default: `{stem}_compressed.mp4`)
- `--level` - `high` (CRF 23), `balanced` (CRF 28) or `max` (CRF 35, smallest file). Default: `balanced`
- `--queue`, `-q` - Add the job to the background queue instead of running it now. See [Queue](queue.md).
- `--recursive`, `--redo` - See [Several files at once](#several-files-at-once)

**Examples:**

```bash
max video compress movie.mp4
max video compress movie.mp4 --level high
max video compress movie.mp4 --level max -o small.mp4
max video compress movie.mp4 --queue
max video compress ~/Videos --level max
```

## convert

Change the video container, for example MKV to MP4.

```bash
max video convert TARGET... [--format FORMAT]
```

Max saves the result next to the input as `{stem}.{format}`. This command has no `-o`.

**Options:**

- `--format`, `-f` - Target format: `mp4`, `mkv` or `avi` (default: `mp4`)
- `--recursive`, `--redo`, `--queue` - See [Several files at once](#several-files-at-once)

## to-audio

Extract the audio track from a video.

```bash
max video to-audio TARGET... [--format FORMAT] [--quality QUALITY] [--output OUTPUT]
```

**Options:**

- `--format`, `-f` - `mp3`, `wav`, `flac` or `aac` (default: `mp3`)
- `--quality`, `-q` - `s` (96k), `m` (128k), `h` (192k) or `x` (320k). Default: `h`
- `--output`, `-o` - Output path (default: `{stem}.{format}`)
- `--recursive`, `--redo`, `--queue` - See [Several files at once](#several-files-at-once)

**Examples:**

```bash
max video to-audio lecture.mp4
max video to-audio lecture.mp4 --format wav
max video to-audio lecture.mp4 -q x
```

## cut

Trim a video. `--start` is required. Pass `--end` or `--duration`, or neither to keep everything up to the end of the file.

```bash
max video cut TARGET... --start TIME [--end TIME | --duration SECONDS] [-o OUTPUT]
```

**Options:**

- `--start`, `-s` - Start time, such as `00:01:00` or `60` (required)
- `--end`, `-e` - End time
- `--duration`, `-d` - Length to keep, such as `10`
- `-o` - Output file (default: `{stem}_cut.mp4`, or `{stem}_cut.mp3` for an audio file)
- `--recursive`, `--queue` - See [Several files at once](#several-files-at-once)

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
max video gif TARGET... [-o OUTPUT] [--width PX] [--fps FPS]
```

**Options:**

- `-o` - Output GIF (default: `{stem}.gif`)
- `--width` - Width in pixels; height scales to match (default: 480)
- `--fps` - Frames per second (default: 15)
- `--recursive`, `--redo`, `--queue` - See [Several files at once](#several-files-at-once)

## snap

Save a JPG screenshot at a timestamp.

```bash
max video snap TARGET... [--time TIME] [-o OUTPUT]
```

**Options:**

- `--time`, `-t` - Timestamp (default: `00:00:05`)
- `-o` - Output image (default: `{stem}_thumb.jpg`)
- `--recursive`, `--redo` - See [Several files at once](#several-files-at-once)

## louder

Raise the volume of a quiet recording.

```bash
max video louder TARGET... [--db DECIBELS] [-o OUTPUT]
```

`TARGET` can be a video or an audio file.

**Options:**

- `--db` - Decibels to add (default: 5.0)
- `-o` - Output file (default: `{stem}_boosted` with the input's extension)
- `--recursive`, `--redo`, `--queue` - See [Several files at once](#several-files-at-once)

## mute

Remove the audio track.

```bash
max video mute TARGET... [-o OUTPUT]
```

**Options:**

- `-o` - Output file (default: `{stem}_mute.mp4`)
- `--recursive`, `--redo`, `--queue` - See [Several files at once](#several-files-at-once)

## brightness

Adjust brightness and contrast.

```bash
max video brightness TARGET... [--brightness VALUE] [--contrast VALUE] [-o OUTPUT]
```

**Options:**

- `--brightness`, `-b` - 0.0 to 2.0, where 1.0 is unchanged (default: 1.0)
- `--contrast`, `-c` - 0.0 to 2.0, where 1.0 is unchanged (default: 1.0)
- `-o` - Output file (default: `{stem}_adjusted.mp4`)
- `--recursive`, `--redo`, `--queue` - See [Several files at once](#several-files-at-once)

## color

Apply a color grading preset.

```bash
max video color TARGET... [--preset PRESET] [-o OUTPUT]
```

**Options:**

- `--preset`, `-p` - `vivid`, `vintage`, `noir`, `warm`, `cool` or `fade` (default: `vivid`)
- `-o` - Output file (default: `{stem}_{preset}.mp4`, such as `trip_noir.mp4`)
- `--recursive`, `--redo`, `--queue` - See [Several files at once](#several-files-at-once)

## stabilize

Smooth out shaky footage.

```bash
max video stabilize TARGET... [-o OUTPUT]
```

**Options:**

- `-o` - Output file (default: `{stem}_stabilized.mp4`)
- `--recursive`, `--redo`, `--queue` - See [Several files at once](#several-files-at-once)

## normalize

Set the audio loudness to a target level.

```bash
max video normalize TARGET... [--level LUFS] [-o OUTPUT]
```

`TARGET` can be a video or an audio file.

**Options:**

- `--level`, `-l` - Target loudness in LUFS (default: -20.0)
- `-o` - Output file (default: `{stem}_normalized` with the input's extension)
- `--recursive`, `--redo`, `--queue` - See [Several files at once](#several-files-at-once)

## denoise

Remove background noise such as hiss, hum, fans or room noise.

```bash
max video denoise TARGET... [OPTIONS]
```

**Options:**

- `--mode`, `-m` - `auto` (general), `hiss` (constant hiss), `hum` (low rumble) or `speech` (RNNoise, best for voice). Default: `auto`
- `--strength`, `-s` - `mild`, `medium` or `aggressive`. Applies to `auto` mode only. Default: `medium`
- `--output`, `-o` - Output file (default: `{stem}_denoised` with the input's extension)
- `--queue`, `-q` - Add the job to the background queue
- `--recursive`, `--redo` - See [Several files at once](#several-files-at-once)

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

# Run it in the background
max video denoise long_clip.mp4 --queue

# Every recording in a folder
max video denoise ~/Recordings --mode speech
```

> **Note**: `auto` mode uses FFmpeg's `anlmdn` filter, which is CPU-heavy. For faster results, try `--mode hiss` or `--mode hum`. Max copies the video stream (`-c:v copy`) and re-encodes only the audio.

## audio-convert

Convert audio between formats, for example WAV to MP3.

```bash
max video audio-convert TARGET... [--format FORMAT] [--quality QUALITY] [-o OUTPUT]
```

`TARGET` can be an audio file or a video file.

**Options:**

- `--format`, `-f` - `mp3`, `aac`, `flac`, `wav` or `ogg` (default: `mp3`)
- `--quality`, `-q` - `s` (128k), `m` (192k) or `h` (320k). Default: `h`
- `-o` - Output file (default: `{stem}.{format}`)
- `--recursive`, `--redo`, `--queue` - See [Several files at once](#several-files-at-once)

**Example:**

```bash
max video audio-convert "*.wav" --format mp3 -q m
```

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
