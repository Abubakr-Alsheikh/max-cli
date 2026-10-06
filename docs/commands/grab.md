# Download (Grab)

Download media from YouTube, Spotify, and 1000+ other sites.

## Usage

```bash
# Download video
max grab download "https://youtube.com/watch?v=..."

# Download audio only
max grab download "https://youtube.com/watch?v=..." -a

# Download in the background and get your terminal back
max grab download "https://youtube.com/watch?v=..." -Q

# Interactive mode (no URL required)
max grab download

# A playlist as an album: Artist/Album folders, tracks numbered 1, 2, 3 ...
max grab download "https://youtube.com/playlist?list=..." -a --sort-into artist/album

# Your own artist and album in every file
max grab download "https://youtube.com/playlist?list=..." -a --artist "Emil Rottmayer" --album "Live 2024"
```

## Options

| Option | Short | Description |
|--------|-------|-------------|
| `--quality` | `-q` | Quality: `ss` (360p), `s` (480p), `m` (720p), `h` (1080p), `x` (4K). Max reads the first letter, so `-q high` works too. Default: your saved quality (`max config grab`) |
| `--resolution` | `-r` | Exact height, such as 144, 240 or 720. Overrides `--quality` |
| `--video` | `-v` | Download video, even when your default type is audio |
| `--audio` | `-a` | Audio only |
| `--subtitles` | `-s` | Download subtitles |
| `--index` | `-i` | Playlist items to download, such as `1` or `1-5` |
| `--no-playlist` | | Download one video, not the playlist |
| `--no-meta` | `--nom` | Skip embedded metadata and thumbnails |
| `--output` | `-o` | Output folder. Default: your download folder (`max config grab`) |
| `--queue` | `-Q` | Add the download to the queue and start the background worker, unless the dashboard or a worker already runs the queue. The command returns at once, and closing the terminal doesn't stop the download. `max queue status` follows it |
| `--no-process` | | Use with `--queue`: add to the queue but don't start the worker. Run `max queue start` or `max queue process` later |
| `--progress` / `--no-progress` | | Show or hide the progress bar (default: show) |
| `--player-client` | | YouTube player client override: `auto`, `default`, `web`, `tv`, `ios`, `android`, `mweb`, `tv_embedded` (fixes HTTP 403 / SABR errors) |
| `--artist` | | Artist to write into every file. Default: what the site says |
| `--album` | | Album to write into every file. Default: the site's album, or the playlist's name |
| `--genre` | | Genre to write into every file |
| `--year` | | Year to write into every file |
| `--track-numbers` / `--no-track-numbers` | | Number a playlist's files by their place in it, as `3/43` (default: on) |
| `--split-title` / `--no-split-title` | | Read the artist from titles like `Artist - Song` when the site names none (default: on) |
| `--sort-into` | | `none` (default), `album` (an `Album/` folder) or `artist/album` (`Artist/Album/`) inside the output folder |

### Tags and folders

With metadata on (the default), Max writes tags into each file: the title, the artist, the album and, for a playlist, the track number.

- **Artist:** `--artist`, else the site's artist, else the part before ` - ` in a title like `A.L.I.S.O.N - Before I Go`, else the channel.
- **Album:** `--album`, else the site's album, else the playlist's name. The playlist's channel becomes the album artist, so music players keep the tracks together.
- **Track:** the item's place in the playlist and the playlist's length (`3/43`). Picking items with `--index 3,5` keeps their real places.
- **Folders:** `--sort-into artist/album` saves into `Artist/Album/`, and `--sort-into album` into `Album/`. A file without an album stays in the artist's folder or the output folder.

Older versions showed track **63** on every downloaded MP3. ffmpeg wrote the link into the old ID3v1 tag, and players read its last character, `?`, as track 63. Max now rewrites that tag after each download, and `max audio` commands ignore the false number. To fix files you already have, renumber them: `max audio batch "<folder>" --start 1`.

`max net` is an old, hidden name for the `max grab` group. It still works, but new scripts should use `max grab`.

### YouTube Troubleshooting

If downloads fail with `HTTP Error 403: Forbidden`, YouTube is probably blocking the default client. Try these fixes:

1. **Install a JavaScript runtime** (required by yt-dlp for YouTube extraction):
   ```bash
   winget install DenoLand.Deno
   ```
2. **Install the PO token provider** (fixes the SABR experiment that blocks music videos):
   ```bash
   max grab pot-setup
   ```
   This installs the yt-dlp plugin (`bgutil-ytdlp-pot-provider`), clones the token server, and sets up its Deno dependencies. Deno must be installed and on your PATH first (step 1). After that, `max grab download` detects the provider and uses the `android` client with token fetching. You don't need extra flags. Pass `--yes` (`-y`) to skip the confirmations. In the dashboard, the Download page's Tools card shows whether the fix is installed and has an "Install fix" button.
3. **Update yt-dlp** to the latest version:
   ```bash
   pip install -U yt-dlp
   ```
4. **Switch the player client yourself**:
   ```bash
   max grab download "https://youtube.com/watch?v=..." --player-client web
   ```

## Interactive Mode

Run without a URL to enter interactive mode:

```bash
max grab download
# Enter a URL and press Enter: Max adds it to the queue and starts downloading
# Enter another URL while the first one downloads
# Press Enter on an empty line (or Ctrl+C) to stop adding URLs
```

- Each URL goes into the download queue, and this terminal downloads them one after another while you type more.
- When the dashboard or the background worker already runs the queue, that process downloads them instead.
- The options you pass (`-a`, `-q`, `-o` and the rest) apply to every URL you enter.
- When you stop, Max waits up to 30 seconds for the downloads still going, then prints how many completed and failed.

## Queue Commands

```bash
# Show the download queue
max grab queue
max grab queue --process    # (-p) Run pending downloads now, in this terminal

# Show download history
max grab history            # The last 10 downloads
max grab history --limit 20 # (-n)
max grab history --clear    # (-c) Delete the download history (asks first; -f skips)

# Clear the queue
max grab clear              # Clear pending downloads
max grab clear --all        # (-a) Clear every queued download that isn't running
max grab clear --force      # (-f) Skip the confirmation prompt

# Show counts: queued, pending, downloading, completed, failed
max grab status
```

`max grab queue --process` leaves the downloads alone when the dashboard or the background worker already runs the queue: that process downloads them.

Downloads share one task store with `max queue` and the dashboard, so
`max queue status` lists queued downloads next to other tasks. The first run
after upgrading moves the old `~/.max_cli/grab_queue.json`,
`grab_history.json` and `download_history.json` into that store and renames
each file to `*.migrated`.

See [Queue](queue.md) for the commands that manage every task type.

## Configuration

Set default download preferences:

```bash
max config grab
```

It asks for:
- Default quality (`s`, `m`, `h` or `x`)
- Whether to strip playlist info from a video link (`watch?v=ID&list=LIST` becomes `watch?v=ID`)
- Whether to embed metadata and thumbnails
- Default type (video or audio)
- Default download folder

## Quality Presets

| Flag | Video | Audio | Best For |
|------|-------|-------|----------|
| `-q ss` | 360p | 64kbps | Slow connections |
| `-q s` | 480p | 64kbps | Data saving |
| `-q m` | 720p | 128kbps | Phone |
| `-q h` | 1080p | 192kbps | Desktop |
| `-q x` | 4K | 320kbps | Best quality |
