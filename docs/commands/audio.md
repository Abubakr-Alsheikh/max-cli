# Audio Metadata Commands

Manage audio file metadata (title, artist, album, genre, etc.) using the `max audio` command group.

## get

Display all metadata from an audio file.

```bash
max audio get <file>
```

**Example:**
```bash
max audio get song.mp3
```

## set

Set metadata on an audio file. Use flags to set specific fields.

```bash
max audio set <file> [OPTIONS]
```

**Options:**
- `--title`, `-t` - Song title
- `--artist`, `-a` - Artist name
- `--album`, `-b` - Album name
- `--album-artist` - Album artist name
- `--genre`, `-g` - Genre
- `--date`, `-d` - Release date (YYYY-MM-DD)
- `--track`, `-n` - Track number
- `--disc` - Disc number
- `--composer` - Composer name
- `--comment`, `-c` - Comment/description
- `--output`, `-o` - Output file (default: overwrite)

**Example:**
```bash
max audio set song.mp3 --artist "The Band" --album "Greatest Hits" --genre "Rock"
```

## clear

Remove all metadata from an audio file.

```bash
max audio clear <file> [OPTIONS]
```

**Options:**
- `--keep-duration/--no-duration` - Preserve audio info (default: keep)
- `--output`, `-o` - Output file

**Example:**
```bash
max audio clear messy_file.mp3
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
- `--track`, `-n` - Track number
- `--start` - Starting track number for auto-increment

**Example:**
```bash
# Set album and artist on all files in a folder
max audio batch "folder/*.mp3" --album "My Album" --artist "John Doe"

# Auto-increment track numbers
max audio batch "folder/*.mp3" --album "My Album" --start 1
```

## Supported Formats

- MP3
- FLAC
- M4A/AAC
- OGG
- WAV
