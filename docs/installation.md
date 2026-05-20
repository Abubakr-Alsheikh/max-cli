# Installation

## Prerequisites

- Python 3.9+
- FFmpeg (for media operations)
- Tesseract OCR (optional, for PDF OCR)

## Install from PyPI

```bash
pip install max-cli
```

## Install Development Version

```bash
git clone https://github.com/Abubakr-Alsheikh/max-cli.git
cd max-cli
pip install -e .[dev]
```

## Install with All Dependencies

```bash
pip install -e .
```

## Optional Dependencies

| Extra | Description |
|-------|-------------|
| `dev` | Development dependencies (pytest, ruff, mypy, mkdocs) |
| `ocr` | OCR support (pytesseract) |
| `ai` | AI features (openai) |
| `tui` | Interactive TUI dashboard (textual) |

## FFmpeg Auto-Resolution

Max automatically detects FFmpeg in your PATH. If not found, you'll be prompted to auto-download it to `~/.max_cli/bin/`. Platform-specific binaries are downloaded and validated automatically.

To manually trigger FFmpeg installation:

```bash
max config setup-ffmpeg
```

## Verify Installation

```bash
max --help
```
