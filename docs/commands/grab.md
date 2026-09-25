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
| `--player-client` | | YouTube player client override: `auto`, `default`, `web`, `tv`, `ios`, `android`, `mweb`, `tv_embedded` (fixes HTTP 403 / SABR errors) |

### YouTube Troubleshooting

If downloads fail with `HTTP Error 403: Forbidden`, YouTube has likely blocked the default client. Fixes:

1. **Install a JavaScript runtime** (required by yt-dlp for YouTube extraction):
   ```bash
   winget install DenoLand.Deno
   ```
2. **Install the PO token provider** (fixes the SABR experiment that blocks music videos):
   ```bash
   max grab pot-setup
   ```
   This installs the yt-dlp plugin (`bgutil-ytdlp-pot-provider`), clones the token server, and sets up its Deno dependencies automatically. Once installed, `max grab` auto-detects it and uses the `android` client with token fetching — no extra flags needed.
3. **Update yt-dlp** to the latest version:
   ```bash
   pip install -U yt-dlp
   ```
4. **Manually switch the player client**:
   ```bash
   max grab download "https://youtube.com/watch?v=..." --player-client web
   ```

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
max grab clear              # Clear pending downloads
max grab clear --all        # Clear every queued download that isn't running

# Show statistics
max grab status
```

Downloads share one task store with `max queue` and the dashboard, so
`max queue status` lists queued downloads next to other tasks. The first run
after upgrading moves the old `~/.max_cli/grab_queue.json`,
`grab_history.json` and `download_history.json` into that store and renames
each file to `*.migrated`.

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
