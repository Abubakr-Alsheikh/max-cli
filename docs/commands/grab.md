# Download (Grab)

Download media from YouTube, Spotify, and 1000+ other sites.

## Usage

```bash
# Download video
max grab download "https://youtube.com/watch?v=..."

# Download audio only
max grab download "https://youtube.com/watch?v=..." -a

# Interactive mode (no URL required)
max grab download
```

## Options

| Option | Short | Description |
|--------|-------|-------------|
| `--quality` | `-q` | Quality: s (480p), m (720p), h (1080p), x (4K) |
| `--video` | `-v` | Force video download |
| `--audio` | `-a` | Audio only (MP3) |
| `--output` | `-o` | Output folder |
| `--no-process` | | Add to queue without processing |
| `--queue` | `-Q` | Add to queue |

## Interactive Mode

Run without a URL to enter interactive mode:

```bash
max grab download
# Enter URL and press Enter - download starts in background
# Enter another URL while the first is downloading
# Press Enter with empty input to exit
```

Benefits:
- Downloads run in background while you add more URLs
- No waiting - enter next URL immediately after previous starts
- Shows progress and status

## Queue Commands

```bash
# Show current download queue
max grab queue

# Show download history
max grab history
max grab history --limit 20

# Clear queue
max grab clear              # Clear pending items
max grab clear --all       # Clear everything including completed

# Show statistics
max grab status
```

## Configuration

Set default download preferences:

```bash
max config grab
```

Options include:
- Default quality
- Auto-strip playlist info
- Embed metadata
- Default type (video/audio)
- Default download folder
- Queue system enabled/disabled

## Quality Presets

| Flag | Video | Audio | Best For |
|------|-------|-------|----------|
| `-q s` | 480p | 64kbps | Data saving |
| `-q m` | 720p | 128kbps | Phone |
| `-q h` | 1080p | 192kbps | Desktop |
| `-q x` | 4K | 320kbps | Best quality |
