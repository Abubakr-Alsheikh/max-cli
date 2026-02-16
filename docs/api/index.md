# API Reference

## Core Modules

- [Core](core.md) - Engine implementations
- [Common](common.md) - Utilities
- [Config](config.md) - Configuration

## Module Overview

### Image Processing

```python
from max_cli.core.image_processor import ImageEngine

engine = ImageEngine()
engine.compress_image("input.jpg", "output.jpg", quality=85)
```

### PDF Operations

```python
from max_cli.core.pdf_engine import PDFEngine

engine = PDFEngine()
engine.merge_pdfs(["file1.pdf", "file2.pdf"], "merged.pdf")
```

### Media Processing

```python
from max_cli.core.media_engine import MediaEngine

engine = MediaEngine()
engine.compress_video("input.mp4", "output.mp4", quality=75)
```

### AI Features

```python
from max_cli.core.ai_engine import AIEngine

engine = AIEngine()
result = engine.categorize_files("/path/to/files")
```
