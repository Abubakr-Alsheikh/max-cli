# Max CLI

A high-performance, modular CLI framework for developers and power users. It provides intelligent automation for media processing, document management, and file organization through a local-first, AI-assisted terminal interface.

## Features

- **Image Processing**: Compress, resize, convert and strip metadata
- **PDF Operations**: Merge, split, compress, OCR, watermark, forms and more
- **Video and Audio**: Compression, audio extraction, noise removal, format conversion
- **Downloads**: Media from YouTube and other sites, with a queue
- **AI Integration**: Ask, chat, image analysis, semantic search, data extraction
- **File Management**: Rename, sort, deduplicate, back up, secure delete and undo

## Quick Start

```bash
# Install
pip install max-cli

# View help
max --help

# Image operations
max images compress photo.jpg
max images resize image.png -w 800

# PDF operations
max pdf compress document.pdf
max pdf merge file1.pdf file2.pdf

# Video operations
max video compress video.mp4
max video to-audio video.mp4

# AI operations
max ai chat
max ai search "invoices from March" ./documents
```

## Why Max CLI?

- **Fast**: Parallel processing, caching, and optimized algorithms
- **Modular**: Plugin system for extensibility
- **Developer-Friendly**: Type hints, comprehensive tests, clear documentation
- **Local-First**: Works offline, no cloud dependency
