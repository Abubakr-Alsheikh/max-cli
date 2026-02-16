# Max CLI

A high-performance, modular CLI framework for developers and power users. It provides intelligent automation for media processing, document management, and file organization through a local-first, AI-assisted terminal interface.

## Features

- **Image Processing**: Compress, resize, convert, and optimize images
- **PDF Operations**: Merge, split, compress, OCR, watermark, and more
- **Media Tools**: Video compression, audio extraction, format conversion
- **AI Integration**: Chat, file categorization, semantic search
- **File Management**: Organize, deduplicate, backup, secure delete

## Quick Start

```bash
# Install
pip install max-cli

# View help
max --help

# Image operations
max images compress photo.jpg
max images resize 800x600 image.png

# PDF operations
max pdf compress document.pdf
max pdf merge file1.pdf file2.pdf

# Media operations
max media compress video.mp4
max media extract-audio video.mp4

# AI operations
max ai chat
max ai categorize ./files
```

## Why Max CLI?

- **Fast**: Parallel processing, caching, and optimized algorithms
- **Modular**: Plugin system for extensibility
- **Developer-Friendly**: Type hints, comprehensive tests, clear documentation
- **Local-First**: Works offline, no cloud dependency
