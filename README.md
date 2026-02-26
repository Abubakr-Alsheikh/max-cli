# Max CLI ⚡

[![PyPI Version](https://img.shields.io/pypi/v/max-cli.svg)](https://pypi.org/project/max-cli/)
[![Python Version](https://img.shields.io/pypi/pyversions/max-cli.svg)](https://pypi.org/project/max-cli/)
[![License](https://img.shields.io/pypi/l/max-cli.svg)](https://github.com/Abubakr-Alsheikh/max-cli/blob/main/LICENSE)
[![Build Status](https://github.com/Abubakr-Alsheikh/max-cli/actions/workflows/ci.yml/badge.svg)](https://github.com/Abubakr-Alsheikh/max-cli/actions)
[![Documentation](https://img.shields.io/badge/docs-MkDocs-blue)](https://Abubakr-Alsheikh.github.io/max-cli/)

> **Your Lazy, Fast Terminal Assistant That Does the Work for You.**

Max transforms complex tasks—like compressing videos, merging PDFs, or downloading from YouTube—into simple commands you can actually remember. Whether you're a casual user or a seasoned developer, Max speaks your language.

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
| **Convert video to audio** | `max video to-audio` | `max video to-audio podcast.mp4` |
| **Download videos/music** | `max grab download` | `max grab download youtube.com/...` |
| **Check download queue** | `max grab queue` | `max grab queue` |
| **Download history** | `max grab history` | `max grab history` |
| **Merge PDFs** | `max pdf bundle` | `max pdf bundle contracts/` |
| **Compress images** | `max img compress` | `max img compress photos/` |
| **Resize images** | `max img resize` | `max img resize logo.png --width 800` |
| **Ask AI anything** | `max ai ask` | `max ai ask "Merge and Compress those pdf files"` |
| **Generate images** | `max ai create` | `max ai create "A cat on a bike"` |
| **Organize files** | `max files smart-sort` | `max files smart-sort downloads/` |

---

## 🚀 Quick Start (5 Minutes)

### Step 1: Install Python

Max runs on Python. If you don't have it:

- **Windows:** Download from [python.org](https://python.org) (check "Add to PATH")
- **Mac:** Open Terminal and run: `brew install python`
- **Linux:** `sudo apt install python3`

### Step 2: Install FFmpeg (For Video/Audio)

Max needs FFmpeg to process videos. Don't worry, it's easy:

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
max grab "https://youtube.com/watch?v=..."

# Compress a video
max video compress mymovie.mp4

# Compress images in a folder
max img compress ./photos
```

---

## 📖 User Guide

### 🎥 Video & Audio

#### Compress Video (Shrink File Size)

```bash
# Simple compression
max video compress video.mp4

# High quality compression
max video compress video.mp4 --preset high

# Specific quality (1-100)
max video compress video.mp4 -q 75
```

#### Convert Video to Audio

```bash
# To MP3 (default, high quality)
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

# First 30 seconds only
max video cut movie.mp4 --duration 30
```

#### Other Video Commands

```bash
max video gif clip.mp4              # Convert to GIF
max video louder audio.mp4 --db 10  # Boost volume by 10dB
max video snap video.mp4 --time 1:30 # Take screenshot at 1:30
max video mute video.mp4             # Remove audio track
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
# Extract pages 1-5 and page 8
max pdf split document.pdf -p 1-5,8
```

#### Compress PDF

```bash
max pdf compress large.pdf
```

#### Add Watermark

```bash
max pdf stamp document.pdf "CONFIDENTIAL"
```

#### Password Protect

```bash
max pdf lock document.pdf
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

# Choose quality: s=480p, m=720p, h=1080p, x=4K
max grab download "..." -q h

# Interactive mode - add URLs and download in background
max grab download

# Download to specific folder
max grab download "..." -o ./my-videos

# Add to queue without processing (batch mode)
max grab download "..." --no-process
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

# Clear completed/failed downloads
max grab clear
```

#### Quality Presets Explained

| Flag | Video Quality | Audio Quality | Best For |
|------|---------------|---------------|----------|
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
# Compress all images in folder (75% quality)
max img compress ./photos

# Compress single image
max img compress photo.jpg

# Force JPEG output
max img compress ./photos --jpeg

# Limit max dimension to 1080px
max img compress ./photos --max 1080
```

#### Resize Images

```bash
# Resize to specific width
max img resize image.png --width 800

# Resize to specific height
max img resize image.png --height 600

# Scale down by percentage
max img resize image.png --scale 50
```

#### Convert Format

```bash
# Convert to WebP (modern, smaller)
max img convert photo.jpg --to webp

# Convert to PNG
max img convert photo.png --to png
```

#### Remove Metadata (Privacy)

```bash
# Strip EXIF data (GPS, camera info, etc)
max img strip ./photos
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

---

### 🔧 System Tools

```bash
# Generate QR code from URL
max share "https://example.com"

# Copy file contents to clipboard
max copy file.txt

# Save clipboard image to file
max paste screenshot.png
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
max config show     # View current configuration
max config grab     # Configure downloader defaults
max config save     # Save local settings as global defaults
```

---

## 💡 Tips & Tricks

### Working with Folders

Most commands work on folders too:

```bash
# Compress ALL images in a folder
max img compress ./videos

# Merge ALL PDFs in a folder
max pdf bundle ./documents
```

### Default Directory

If you don't specify a path, Max uses the current folder:

```bash
cd ./myphotos
max img compress   # Compresses everything in myphotos
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
max img --help
max pdf --help
```

---

## 🆘 Troubleshooting

### "FFmpeg not found"

Install FFmpeg (see Step 2 above) and restart your terminal.

### "API key not found"

Run `max config setup` to configure your AI provider.

### "Permission denied" (Windows)

Run Command Prompt as Administrator, or use a virtual environment.

### Something else not working?

- Check: `max --version`
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

Max CLI supports plugins for extensibility. Plugins are stored in:
- `~/.max_cli/plugins/` (user-level)
- `./plugins/` (project-level)

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
│   │   ├── media_engine.py
│   │   ├── network_engine.py
│   │   ├── pdf_engine.py
│   │   ├── queue_manager.py
│   │   └── system_engine.py
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
