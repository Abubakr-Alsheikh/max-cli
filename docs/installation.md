# Installation

## Prerequisites

- Python 3.9+
- FFmpeg (for media operations; Max can download it for you)
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

## Install from Source

```bash
pip install -e .
```

The base install includes the AI, PDF, image and download features. Add an extra from the table below for OCR or the dashboard, for example `pip install -e .[ocr,tui]`.

## Optional Dependencies

| Extra | Description |
|-------|-------------|
| `dev` | Development dependencies (pytest, ruff, mypy, mkdocs) |
| `ocr` | OCR support (pytesseract) |
| `tui` | Interactive TUI dashboard (textual, psutil) |

## FFmpeg Auto-Resolution

Max looks for FFmpeg on your PATH. If it can't find it, Max offers to download a binary for your platform into `~/.max_cli/bin/` and checks that it runs.

To install FFmpeg ahead of time:

```bash
max config setup-ffmpeg
```

## Verify Installation

```bash
max --help
```
