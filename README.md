# Max CLI ⚡

[![PyPI Version](https://img.shields.io/pypi/v/max-cli.svg)](https://pypi.org/project/max-cli/)
[![Python Version](https://img.shields.io/pypi/pyversions/max-cli.svg)](https://pypi.org/project/max-cli/)
[![License](https://img.shields.io/pypi/l/max-cli.svg)](https://github.com/Abubakr-Alsheikh/max-cli/blob/main/LICENSE)
[![Build Status](https://github.com/Abubakr-Alsheikh/max-cli/actions/workflows/ci.yml/badge.svg)](https://github.com/Abubakr-Alsheikh/max-cli/actions)
[![Documentation](https://img.shields.io/badge/docs-MkDocs-blue)](https://Abubakr-Alsheikh.github.io/max-cli/)

> **Your Lazy, Fast Terminal Assistant That Does the Work for You.**

Max turns multi-step jobs, like compressing a video, merging PDFs or downloading from YouTube, into short commands you can remember.

---

## 📚 Documentation

**Full docs:** https://Abubakr-Alsheikh.github.io/max-cli/

**Quick links:**
- [Installation](https://Abubakr-Alsheikh.github.io/max-cli/installation/)
- [Usage](https://Abubakr-Alsheikh.github.io/max-cli/usage/)
- [Commands](https://Abubakr-Alsheikh.github.io/max-cli/commands/)
- [API Reference](https://Abubakr-Alsheikh.github.io/max-cli/api/)
- [Contributing](https://Abubakr-Alsheikh.github.io/max-cli/contributing/)

---

## 🤔 What Can Max Do?

| Task | Max Command | Example |
|------|-------------|---------|
| **Compress videos** | `max video compress` | `max video compress movie.mp4` |
| **Remove background noise** | `max video denoise` | `max video denoise recording.mp4` |
| **Audio noise removal** | `max audio denoise` | `max audio denoise podcast.mp3` |
| **Convert video to audio** | `max video to-audio` | `max video to-audio podcast.mp4` |
| **Compress audio** | `max audio compress` | `max audio compress recording.wav` |
| **Get audio metadata** | `max audio get` | `max audio get song.mp3` |
| **Set audio metadata** | `max audio set` | `max audio set song.mp3 --artist "Artist" --album "Album"` |
| **Batch organize audio** | `max audio batch` | `max audio batch "folder/*.mp3" --album "My Album" --artist "Band"` |
| **Organize to folders** | `max audio organize` | `max audio organize "*.mp3" --pattern artist` |
| **Download videos/music** | `max grab download` | `max grab download youtube.com/...` |
| **Check download queue** | `max grab queue` | `max grab queue` |
| **Download history** | `max grab history` | `max grab history` |
| **Fix YouTube 403 errors** | `max grab pot-setup` | `max grab pot-setup` |
| **Merge PDFs** | `max pdf bundle` | `max pdf bundle contracts/` |
| **OCR scanned PDFs** | `max pdf ocr` | `max pdf ocr scan.pdf` |
| **Fill PDF forms** | `max pdf form-fill` | `max pdf form-fill form.pdf -f name="John"` |
| **Compress images** | `max images compress` | `max images compress photos/` |
| **Resize images** | `max images resize` | `max images resize logo.png -w 800` |
| **Ask AI anything** | `max ai ask` | `max ai ask "Merge and Compress those pdf files"` |
| **Generate images** | `max ai create` | `max ai create "A cat on a bike"` |
| **Search files by meaning** | `max ai search` | `max ai search "tax receipts" ./docs` |
| **Organize files** | `max files smart-sort` | `max files smart-sort downloads/` |
| **Find duplicates** | `max files duplicates` | `max files duplicates downloads/ -r` |
| **Undo file ops** | `max files undo` | `max files undo` |
| **File history** | `max files history` | `max files history -v` |
| **Background jobs** | `max queue` | `max queue status` |
| **QR code for a URL** | `max tools share` | `max tools share "http://192.168.1.20:8000"` |
| **TUI Dashboard** | `max` | `max` (or `max dashboard`) |

---

## 🚀 Quick Start (5 Minutes)

### Step 1: Install Python

Max runs on Python. If you don't have it:

- **Windows:** Download from [python.org](https://python.org) (check "Add to PATH")
- **Mac:** Open Terminal and run: `brew install python`
- **Linux:** `sudo apt install python3`

### Step 2: Install FFmpeg (For Video/Audio)

Max automatically detects and downloads FFmpeg if it's not in your PATH. On first use of a video/audio command, you'll be prompted to auto-install it to `~/.max_cli/bin/`.

To manually install FFmpeg:

```bash
max config setup-ffmpeg
```

Or install via your package manager:

```bash
# Mac
brew install ffmpeg

# Windows (run in PowerShell or Command Prompt)
winget install Gyan.FFmpeg

# Linux
sudo apt install ffmpeg
```

### Step 3: Install Max

```bash
# Clone and install
git clone https://github.com/Abubakr-Alsheikh/max-cli.git
cd max-cli
pip install -e .
```

### Step 4: Configure AI (Optional but Recommended)

Max's AI features need an API key. The easiest setup:

```bash
max config setup
```

This wizard will guide you through:

- Choosing your AI provider (Google Gemini, OpenAI, Ollama, or custom)
- Entering your API key (not needed for Ollama)
- Setting preferences

**AI Provider Options:**

| Provider | API Key Required | Best For |
|----------|------------------|----------|
| [Google Gemini](https://aistudio.google.com/app/apikey) | Yes | Free tier, vision support |
| [OpenAI](https://platform.openai.com/api-keys) | Yes | GPT models, image generation |
| **Ollama** | No | Local/private AI, no internet needed |

**Using Ollama (Local AI):**

If you want to run AI locally without an internet connection:

1. Install [Ollama](https://ollama.com)
2. Run `max config setup` and select "ollama"
3. Choose your model (e.g., llama3, mistral, codellama)

```bash
# Example Ollama .env settings
OLLAMA_ENABLED=true
OLLAMA_MODEL=llama3
OPENAI_BASE_URL=http://localhost:11434/v1
OPENAI_API_KEY=ollama
```

### Step 5: Start Using Max

```bash
# See all available commands
max --help

# Download a video
max grab download "https://youtube.com/watch?v=..."

# Compress a video
max video compress mymovie.mp4

# Compress images in a folder
max images compress ./photos
```

---

## 📖 User Guide

### 🎥 Video & Audio

#### Compress Video (Shrink File Size)

```bash
# Default compression (balanced, CRF 28)
max video compress video.mp4

# Better quality, bigger file (CRF 23)
max video compress video.mp4 --level high

# Smallest file (CRF 35)
max video compress video.mp4 --level max

# Add to the background queue instead of running now
max video compress video.mp4 --queue
```

#### Convert Video to Audio

```bash
# To MP3 (default quality h = 192k)
max video to-audio lecture.mp4

# To WAV (lossless, for editing)
max video to-audio lecture.mp4 --format wav

# To MP3 320kbps
max video to-audio lecture.mp4 -q x
```

#### Trim/Cut Video

```bash
# Cut from 0:30 to 1:00
max video cut movie.mp4 --start 0:30 --end 1:00

# First 30 seconds only (--start is required)
max video cut movie.mp4 --start 0 --duration 30
```

#### Other Video Commands

```bash
max video denoise recording.mp4      # Remove background noise
max video gif clip.mp4               # Convert to GIF
max video louder audio.mp4 --db 10   # Boost volume by 10dB
max video snap video.mp4 --time 1:30 # Take screenshot at 1:30
max video mute video.mp4             # Remove audio track
max video concat "*.mp4" -o all.mp4  # Join videos (--method fast|safe)
```

---

### 📄 PDF Documents

#### Merge PDFs

```bash
# Merge all PDFs in a folder
max pdf bundle mydocs/

# Merge specific files
max pdf bundle file1.pdf file2.pdf
```

#### Split PDF

```bash
# Keep pages 1-5
max pdf split document.pdf -s 1 -e 5

# Remove pages 5-10
max pdf split document.pdf --remove -s 5 -e 10

# Split into files of 10 pages each
max pdf split document.pdf -c 10
```

#### Compress PDF

```bash
# Defaults: 150 DPI, JPEG quality 80
max pdf compress large.pdf

# Smaller file
max pdf compress large.pdf --dpi 100 --quality 60
```

#### Add Watermark

```bash
max pdf stamp document.pdf "CONFIDENTIAL"
```

#### Password Protect

```bash
max pdf lock document.pdf --password "s3cret"
```

#### OCR (Scanned PDFs)

Needs Tesseract and the `ocr` extra (`pip install max-cli[ocr]`).

```bash
# Writes document.txt
max pdf ocr document.pdf

# German and English
max pdf ocr document.pdf --lang eng+deu
```

#### Forms

```bash
# Print the form fields
max pdf form-data form.pdf

# Fill fields (repeat -f)
max pdf form-fill form.pdf -f name="John" -f email="john@example.com"

# Make the fields uneditable
max pdf form-flatten form_filled.pdf
```

#### Optimize and Compare

```bash
# Remove unused objects, compress images, linearize for the web
max pdf optimize document.pdf

# Show which pages differ between two PDFs
max pdf compare old.pdf new.pdf
```

---

### 📥 Downloading (YouTube, Spotify, etc.)

Download from almost any website:

```bash
# Download video (best quality)
max grab download "https://youtube.com/watch?v=..."

# Download audio only (MP3)
max grab download "https://youtube.com/watch?v=..." -a

# Force video download (override default)
max grab download "https://youtube.com/watch?v=..." -v

# Choose quality: ss=360p, s=480p, m=720p, h=1080p, x=4K
max grab download "..." -q h

# Interactive mode - add URLs and download in background
max grab download

# Download to specific folder
max grab download "..." -o ./my-videos

# Add to queue without processing (batch mode)
max grab download "..." --no-process

# Fix YouTube HTTP 403 errors: install the PO token provider once
max grab pot-setup

# Or switch player client manually
max grab download "..." --player-client web
```

#### Interactive Mode

Run `max grab download` without a URL to enter interactive mode:

```bash
max grab download
# Enter URL and press Enter - download starts in background
# Enter another URL while the first is downloading
# Press Enter with empty input to exit
```

#### Queue System

```bash
# Check download queue
max grab queue

# Show download history
max grab history

# Clear pending downloads (--all clears everything that isn't running)
max grab clear
```

Downloads share one task store with `max queue`, so `max queue status` lists them too.

#### Quality Presets Explained

| Flag | Video Quality | Audio Quality | Best For |
|------|---------------|---------------|----------|
| `-q ss` | 360p | 64kbps | Slow connections |
| `-q s` | 480p | 64kbps | Saving data |
| `-q m` | 720p | 128kbps | Phone viewing |
| `-q h` | 1080p | 192kbps | Desktop viewing |
| `-q x` | 4K | 320kbps | Best quality |

#### Save Your Download Preferences

```bash
# Set your defaults once
max config grab

# Configure:
# - Default quality (s/m/h/x)
# - Auto-strip playlist info
# - Embed metadata
# - Default type (video/audio)
# - Default download folder
# - Enable/disable queue system
```

---

### 🖼 Images

#### Compress Images

```bash
# Compress all images in a folder (quality from DEFAULT_QUALITY, 85 by default; results go to photos_optimized/)
max images compress ./photos

# Compress a single image with quality 70
max images compress photo.jpg -q 70

# Force JPEG output
max images compress ./photos --jpeg

# Limit the longest side to 1080px
max images compress ./photos -m 1080
```

#### Resize Images

```bash
# Resize to specific width
max images resize image.png -w 800

# Resize to specific height
max images resize image.png -h 600

# Scale down by percentage
max images resize image.png -s 50
```

#### Convert Format

```bash
# Convert to WebP (modern, smaller)
max images convert photo.jpg --to webp

# Convert to PNG
max images convert photo.jpg --to png
```

#### Remove Metadata (Privacy)

```bash
# Strip EXIF data (GPS, camera info, etc)
max images strip ./photos
```

---

### 🤖 AI Assistant

Max has a smart AI that understands what you want.

#### Ask Anything

```bash
# Get help with a task
max ai ask "How do I compress this video?"

# In a folder with a file, just describe what you want
max ai ask "Make this image smaller"
# Max figures out which file you mean!
```

#### Analyze Images

```bash
# Analyze a screenshot
max ai analyze screenshot.png -p "What error is shown?"

# Extract data from receipt
max ai analyze receipt.jpg -p "What is the total amount?"
```

#### Generate Images

```bash
# Create from text description
max ai create "A cute cat sitting on a beach" -o cat.png

# Edit existing image
max ai edit photo.jpg "Add a sunset background" -o new_photo.jpg
```

#### Chat Mode

```bash
# Start an interactive conversation
max ai chat
```

#### Search Files by Meaning

```bash
# Searches txt, md, py, json and yaml files by default (one AI request per file)
max ai search "notes about the Q3 budget" ./notes

# Pick the extensions
max ai search "database settings" . --ext py,yaml
```

#### Extract Structured Data

```bash
# Pull fields out of a receipt and save them as JSON
max ai extract receipt.jpg -s "total:Total amount" -s "date:Date" -o receipt.json
```

---

### 📂 File Management

#### Smart Sort (AI Organizer)

```bash
# Automatically organize files into categories
max files smart-sort ./downloads

# Max reads filenames and sorts them into folders like:
# Invoices/, Images/, Documents/, etc.
```

#### Rename Sequentially

```bash
# Rename to 1_file, 2_file, etc.
max files order ./photos
```

#### Undo File Operations

```bash
# Reverse the last file operation
max files undo

# View operation history
max files history

# Verbose history with individual file paths
max files history -v
```

#### Find Duplicates

```bash
# List duplicate files (add -r to scan subfolders)
max files duplicates ./downloads -r

# Delete duplicates, keeping one copy. Max asks first.
max files duplicates ./downloads -r --delete

# Delete without asking
max files duplicates ./downloads -r --delete --force
```

#### Secure Delete

```bash
# Overwrite 3 times, then delete. Max asks first.
max files shred secrets.txt

# 7 passes, no prompt
max files shred secrets.txt -p 7 --force
```

#### Backups

```bash
# Copy a file into ~/.max_cli/backups/
max files backup report.docx

# List backups, or restore one
max files backups
max files backups --restore <backup-path>

# Delete backups older than 30 days
max files backup-cleanup --days 30
```

Max records `order`, `smart-sort`, `duplicates --delete` and `audio organize` so `max files undo` can reverse them. Before `duplicates --delete` deletes anything, Max saves a backup. `shred` keeps no copy and can't be undone.

---

### 🖥 TUI Dashboard

Type `max` on its own and the dashboard opens. From there you can download media, run tools, watch the queue and chat with the AI. The dashboard comes with the base install.

```bash
max              # opens the dashboard in a terminal
max dashboard    # the same, by name
```

In a script, a pipe or CI, a bare `max` prints the help text instead, so nothing waits for key presses.

**Dashboard Sections:**

| Section | Description |
|---------|-------------|
| **Home** | Quick actions |
| **Download** | Download form with progress |
| **Queue** | Live task queue with progress |
| **History** | Filterable task history |
| **Files** | File browser |
| **Tools** | A form for each command, with all its options |
| **Analytics** | Live usage and system monitoring |
| **Config** | Editable configuration panel |
| **System** | Disk usage and system info |
| **Chat** | AI chat |

Press `q` to quit, `r` to refresh and `Ctrl+B` to collapse the sidebar.

---

### 🔧 System Tools

```bash
# Show a QR code for a URL in the terminal
max tools share "https://example.com"

# Copy file contents to clipboard
max tools copy file.txt

# Save clipboard image to file (default: clipboard.png)
max tools paste screenshot.png
```

---

### ⏳ Background Queue

Heavy commands can add a job to a queue instead of running it now. `max video compress` and `max video denoise` take `--queue` (`-q`); `max grab download` takes `--queue` (`-Q`).

```bash
# Queue a job
max video compress movie.mp4 --queue

# See what's waiting
max queue status

# Run pending jobs (--max N to stop after N)
max queue process

# Counts by status and type
max queue stats

# Finished tasks, optionally one type
max queue history --type video_compress

# Cancel or retry a task by ID
max queue cancel <task-id>
max queue retry <task-id>

# Remove pending tasks (--failed for failed ones, --all for everything not running)
max queue clear
```

---

## ⚙️ Configuration

### Setting Up Your API Key

The easiest way:

```bash
max config setup
```

### Manual Configuration

Create a `.env` file in your project folder:

```ini
# For Google Gemini (recommended - has free tier)
OPENAI_API_KEY=your_api_key_here
OPENAI_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai/
AI_MODEL=gemini-1.5-flash
AI_IMAGE_MODEL=gemini-2.0-flash-exp

# For OpenAI
OPENAI_API_KEY=sk-...
OPENAI_BASE_URL=https://api.openai.com/v1
AI_MODEL=gpt-4o-mini

# Default settings
DEFAULT_QUALITY=80
GRAB_QUALITY=h
GRAB_AUDIO_FORMAT=mp3
GRAB_DEFAULT_PATH=~/Max Downloads
GRAB_DEFAULT_TYPE=video
GRAB_QUEUE_ENABLED=true
```

### Configuration Locations

- **Global:** `~/.max_config.env` - Applied everywhere
- **Local:** `.env` - Applied to current folder

Local settings override global settings.

### Other Config Commands

```bash
max config show             # View current configuration
max config validate         # Check your settings
max config grab             # Configure downloader defaults
max config save             # Save local settings as global defaults
max config reset            # Delete config files (--global or --local for one)
max config export           # Save settings to max-config.json (-o to rename)
max config import cfg.json  # Load settings from JSON
max config setup-ffmpeg     # Download and install FFmpeg
```

`max config export` leaves your API key out. Add `--include-secrets` to include it, and keep that file private.

---

## 💡 Tips & Tricks

### Working with Folders

Most commands work on folders too:

```bash
# Compress ALL images in a folder
max images compress ./photos

# Merge ALL PDFs in a folder
max pdf bundle ./documents
```

### Default Directory

If you don't specify a path, Max uses the current folder:

```bash
cd ./myphotos
max images compress   # Compresses everything in myphotos
```

### Chain Commands

You can run multiple commands:

```bash
# Merge PDFs then compress
max pdf bundle ./docs && max pdf compress merged.pdf
```

### Get Help

```bash
# See all commands
max --help

# See help for specific command
max video --help
max images --help
max pdf --help
```

---

### Exit codes for scripts

`max` exits 0 when a command succeeds and 1 when it reports an error, even if it kept going after the error (for example one failed file in a batch). Usage mistakes such as a bad option exit 2. You can check `$?` or `%ERRORLEVEL%` in scripts.

## 🆘 Troubleshooting

### "FFmpeg not found"

Max now auto-downloads FFmpeg on first use. Run `max config setup-ffmpeg` to install manually, or accept the prompt when running a video/audio command.

### "API key not found"

Run `max config setup` to configure your AI provider.

### "Permission denied" (Windows)

Run Command Prompt as Administrator, or use a virtual environment.

### Something else not working?

- Check your version: `pip show max-cli`
- Get help: `max --help`
- Report issues: [GitHub Issues](https://github.com/Abubakr-Alsheikh/max-cli/issues)

---

## 🔧 For Developers

### Installation (Development Mode)

```bash
# Clone
git clone https://github.com/Abubakr-Alsheikh/max-cli.git
cd max-cli

# Install with dev dependencies
pip install -e .[dev]

# Run tests
pytest tests/

# Lint code
ruff check .
ruff format .

# Type check
mypy src/

# Run the GitHub CI checks locally before you push
python scripts/ci_local.py --full
```

### Documentation

Full documentation is available at: https://Abubakr-Alsheikh.github.io/max-cli/

Local documentation development:

```bash
# Install mkdocs
pip install mkdocs mkdocs-material

# Serve locally
mkdocs serve

# Build for production
mkdocs build
```

### Plugin System

Max CLI supports plugins for extensibility. Plugins load from `~/.max_cli/plugins/`.

To load plugins from another folder, list it under `"plugin_dirs"` in `~/.max_cli/plugins.json`:

```json
{"enabled": {}, "plugin_dirs": ["~/code/my-max-plugins"]}
```

Max CLI never loads plugins from the current directory. A cloned repository cannot run code just because you ran `max` inside it.

#### Plugin Commands

```bash
# List all installed plugins
max plugins list
max plugins list --all    # Include disabled plugins

# Get detailed info about a plugin
max plugins info <plugin-name>

# Enable or disable a plugin
max plugins enable <plugin-name>
max plugins disable <plugin-name>
```

#### Creating a Plugin

```python
import typer
from max_cli.plugins.base import CLIPlugin


class MyPlugin(CLIPlugin):
    """My custom plugin."""

    def __init__(self):
        super().__init__(
            name="my-plugin",
            version="1.0.0",
            description="My custom plugin description",
            author="Your Name",
            author_email="you@example.com",
            url="https://github.com/you/plugin",
            license="MIT",
            tags=["custom", "example"],
        )

    @property
    def priority(self) -> int:
        """Lower = registered first. Default is 100."""
        return 100

    def validate(self) -> tuple[bool, str | None]:
        """Validate plugin requirements."""
        return True, None

    def on_load(self, context) -> None:
        """Called when plugin loads."""
        pass

    def on_unload(self) -> None:
        """Called when plugin unloads."""
        pass

    def register(self, app: typer.Typer) -> None:
        @app.command("my-command")
        @app.command("mc")  # Alias
        def my_command(
            name: str = typer.Option("World", "--name", "-n", help="Name to greet"),
        ) -> None:
            """My custom command."""
            typer.echo(f"Hello, {name}!")


# IMPORTANT: Instantiate at module level
plugin = MyPlugin()
```

For detailed documentation, see `PLANS/docs/plugins.md`.

### Architecture

```
src/max_cli/
├── core/
│   ├── engines/          # Business logic (AI, media, PDF, etc.)
│   │   ├── ai_engine.py
│   │   ├── file_organizer.py
│   │   ├── image_processor.py
│   │   ├── media_engine.py   # Facade over video/audio/stream engines
│   │   ├── video_engine.py
│   │   ├── audio_engine.py
│   │   ├── stream_engine.py
│   │   ├── network_engine.py
│   │   ├── pdf_engine.py
│   │   ├── system_engine.py
│   │   └── task_manager.py  # Task queue and history (queue, grab, TUI)
│   └── cli/              # CLI command registration
│       ├── commands/     # Command modules
│       ├── plugins.py    # Plugin lifecycle
│       └── registry.py   # Command registry
├── interface/            # Typer CLI command interfaces
├── common/              # Shared utilities and exceptions
└── __init__.py          # Package exports
```

---

## 🤝 Contributing

Found a bug or have a feature request?

See [CONTRIBUTING.md](CONTRIBUTING.md) for detailed guidelines.

1. Open an issue: [GitHub Issues](https://github.com/Abubakr-Alsheikh/max-cli/issues)
2. Fork the repo
3. Submit a PR

---

## 📄 License

MIT License - Free to use, modify, and distribute.

---

## 🙏 Thank You

Max was built to make your life easier. If you find it useful, star the repo and share it with others!

Questions? Reach out or open an issue.

<div style="text-align: center;">
Build with 💗 to make life easier
</div>
