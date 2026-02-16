# Usage

## Basic Usage

```bash
max --help
```

## Image Operations

```bash
# Compress image
max images compress photo.jpg

# Resize image
max images resize 800x600 image.png

# Convert format
max images convert image.jpg output.png

# Strip metadata
max images strip photo.jpg
```

## PDF Operations

```bash
# Compress PDF
max pdf compress document.pdf

# Merge PDFs
max pdf merge file1.pdf file2.pdf

# Split PDF
max pdf split document.pdf

# OCR
max pdf ocr document.pdf

# Watermark
max pdf watermark document.pdf watermark.png
```

## Media Operations

```bash
# Compress video
max media compress video.mp4

# Extract audio
max media extract-audio video.mp4

# Convert format
max media convert video.mp4 output.avi

# Trim video
max media trim video.mp4 --start 0 --end 30

# Concatenate videos
max media concat "*.mp4"
```

## AI Operations

```bash
# Chat mode
max ai chat

# Categorize files
max ai categorize ./files

# Semantic search
max ai search "query" ./directory

# Generate image
max ai generate "a beautiful sunset"
```

## File Operations

```bash
# Organize files
max files organize ./photos

# Find duplicates
max files duplicates ./downloads

# Secure delete
max files shred sensitive.txt

# Backup
max files backup ./directory
```

## Configuration

```bash
# Show config
max config show

# Set value
max config set MAX_WORKERS 8

# Export config
max config export config.json
```
