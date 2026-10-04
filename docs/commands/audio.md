# Audio Commands

Manage audio files: read/write metadata, compress large recordings, and organize your music library using the `max audio` command group.

Tags use the same names in every format (title, artist, album ...). `batch` and `organize` take files, a folder (its audio files, not those in subfolders) or a pattern such as `"*.mp3"`. The dashboard's Audio page runs every command here.

## Several files at once

`compress`, `denoise` and `clear` take several files, a folder or a pattern as well as one file:

```bash
max audio compress a.wav b.wav                # these two files
max audio compress ~/Recordings --recursive   # every audio file in the folder and its subfolders
max audio denoise "*.m4a" --queue             # every M4A here, as background jobs
```

- A folder gives you its audio files. Max leaves out hidden files and folders.
- Quote a pattern (`"*.m4a"`) so Max expands it, not your shell.
- `--recursive` looks in subfolders too.
- With a folder or a pattern, `compress` and `denoise` skip a file whose result already exists (`a.wav` when `a_compressed.mp3` is there) and don't treat their own earlier results as new input. `--redo` runs those files again. Files you name one by one always run.
- Max runs up to four files at a time and ticks off each one as it finishes. When a file fails, the others still run; Max lists the failures at the end and exits with code 1.
- `-o` names one file, so Max refuses it with several. Each result goes next to its file.
- `clear` with several files asks once before it changes them, unless you turned `CONFIRM_DESTRUCTIVE` off.
- `--queue` (`compress` and `denoise`) adds one job per file to the background queue and starts a background worker. The worker keeps going after you close the terminal. Run `max queue status` to watch it. See [Queue](queue.md). `-q` means `--quality`, so `--queue` has no short form here.

## compress

Compress an audio file by re-encoding to a lower bitrate. Use it to shrink large recordings. A 4-minute WAV at 80MB becomes an MP3 of about 3MB.

```bash
max audio compress <file>... [OPTIONS]
```

**Options:**
- `--output`, `-o` - Output audio file path (default: `{stem}_compressed.mp3`)
- `--quality`, `-q` - Quality preset: `s` (64k), `m` (96k), `h` (128k), `x` (192k) (default: `h`)
- `--mono`, `-m` - Convert to mono for maximum compression
- `--recursive`, `--redo`, `--queue` - See [Several files at once](#several-files-at-once)

**Examples:**
```bash
# Default compression (128k MP3)
max audio compress recording.wav

# Maximum compression (64k mono MP3)
max audio compress recording.wav -q s --mono

# Custom output file
max audio compress recording.wav -o recording_compressed.mp3 -q m

# Every audio file in a folder, in the background
max audio compress ~/Recordings --queue
```

## denoise

Remove background noise from audio files (hiss, hum, fan, ambient noise).

```bash
max audio denoise <file>... [OPTIONS]
```

**Options:**
- `--mode`, `-m` - Denoise mode: `auto` (general), `hiss` (constant hiss), `hum` (low rumble), `speech` (RNNoise, best for voice) (default: `auto`)
- `--strength`, `-s` - Denoising strength: `mild`, `medium`, `aggressive` (auto mode only, default: `medium`)
- `--output`, `-o` - Output file (default: `{stem}_denoised` with the input's extension)
- `--recursive`, `--redo`, `--queue` - See [Several files at once](#several-files-at-once)

**Examples:**
```bash
# Auto-denoise a podcast recording
max audio denoise podcast.mp3

# Remove background hiss from a recording
max audio denoise interview.wav --mode hiss

# Best for speech and podcasts (RNNoise neural network)
max audio denoise interview.wav --mode speech

# Apply heavy denoising
max audio denoise noisy_recording.mp3 --strength aggressive

# Specify output file
max audio denoise lecture.mp3 -o cleaned_lecture.mp3
```

## get

Show an audio file's tags in a fixed order (title, artist, album, album artist, genre, date, track, disc, composer, comment, then any other tag), then its length, bitrate, sample rate and channels.

```bash
max audio get <file>
```

**Example:**
```bash
max audio get song.mp3
```

## set

Set metadata on an audio file. Use flags to set specific fields; tags you don't pass stay as they are. With no flag at all, Max stops with exit code 1.

```bash
max audio set <file> [OPTIONS]
```

**Options:**
- `--title`, `-t` - Song title
- `--artist`, `-a` - Artist name
- `--album`, `-b` - Album name
- `--album-artist` - Album artist name
- `--genre`, `-g` - Genre
- `--date`, `-d` - Release date (2024 or 2024-05-01)
- `--track`, `-n` - Track number (3, or 3/12)
- `--disc` - Disc number
- `--composer` - Composer name
- `--comment`, `-c` - Comment/description
- `--output`, `-o` - Output file (default: overwrite)

**Example:**
```bash
max audio set song.mp3 --artist "The Band" --album "Greatest Hits" --genre "Rock"
```

## clear

Remove all metadata from an audio file. The audio itself, and so its length, stays the same.

```bash
max audio clear <file>... [OPTIONS]
```

**Options:**
- `--output`, `-o` - Write the cleared copy here and leave the original as it is (default: change the file in place)
- `--recursive` - See [Several files at once](#several-files-at-once)

`--keep-duration` and `--no-duration` still run but do nothing: clearing tags never touched the audio.

**Example:**
```bash
max audio clear messy_file.mp3

# Every audio file in a folder (asks once first)
max audio clear ~/Music/Imports
```

## batch

Set the same metadata on multiple audio files at once. Useful for organizing files into an album.

```bash
max audio batch <files...> [OPTIONS]
```

**Options:**
- `--title`, `-t` - Song title
- `--artist`, `-a` - Artist name
- `--album`, `-b` - Album name
- `--album-artist` - Album artist name
- `--genre`, `-g` - Genre
- `--date`, `-d` - Release date
- `--track`, `-n` - One track number for every file
- `--start` - First track number; Max numbers the files in order from here
- `--disc` - Disc number
- `--composer` - Composer name
- `--comment`, `-c` - Comment

A file that fails is reported and the rest go on.

**Example:**
```bash
# Set album and artist on all files in a folder
max audio batch "folder/*.mp3" --album "My Album" --artist "John Doe"

# Auto-increment track numbers
max audio batch "folder/*.mp3" --album "My Album" --start 1

# A folder works too
max audio batch folder --genre Jazz
```

## organize

Move audio files into folders based on their metadata. `max files undo` reverses the moves.

```bash
max audio organize <files...> [OPTIONS]
```

**Options:**
- `--output`, `-o` - Target directory (default: same as source)
- `--pattern`, `-p` - Folder structure: `artist`, `album`, `genre`, `artist-album` or `contributing-artists` (default: `artist`)
- `--filter`, `-f` - Only organize files inside a folder with this name, such as `--filter 'Electronic Gems'`
- `--dry-run` - Show where each file would go and move nothing

**Patterns:**
- `artist` - `Music/Artist Name/Song.mp3`
- `album` - `Music/Album Name/Song.mp3`
- `genre` - `Music/Rock/Song.mp3`
- `artist-album` - `Music/Artist Name/Album Name/Song.mp3`
- `contributing-artists` - `Music/Contributing Artist/Song.mp3` (uses the album artist tag, or the artist tag when that is empty)

**Example:**
```bash
# Organize all MP3s by artist (default)
max audio organize "downloads/*.mp3"

# Organize by album into a specific folder
max audio organize "downloads/*.mp3" --output "Music Library" --pattern album

# Organize by artist and album
max audio organize "downloads/*.mp3" --pattern artist-album

# See the moves first
max audio organize downloads --pattern artist-album --dry-run
```

## Supported Formats

- MP3
- FLAC
- M4A/AAC
- OGG
- Opus
- WAV
