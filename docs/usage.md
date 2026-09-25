# Usage

## Basic Usage

```bash
max --help
max <group> --help
max <group> <command> --help
```

## Image Operations

```bash
# Compress every image in a folder
max images compress ./photos

# Resize to 800px wide
max images resize image.png -w 800

# Convert to WebP
max images convert photo.jpg --to webp

# Strip metadata
max images strip photo.jpg
```

## PDF Operations

```bash
# Compress a PDF
max pdf compress document.pdf

# Merge PDFs
max pdf merge file1.pdf file2.pdf -o merged.pdf

# Keep pages 1-5
max pdf split document.pdf -s 1 -e 5

# OCR a scanned PDF
max pdf ocr document.pdf

# Watermark every page
max pdf stamp document.pdf "CONFIDENTIAL"
```

## Video Operations

```bash
# Compress a video
max video compress video.mp4

# Extract the audio
max video to-audio video.mp4

# Change the container
max video convert video.mkv --format mp4

# Keep the first 30 seconds
max video cut video.mp4 --start 0 --end 30

# Join videos
max video concat "*.mp4" -o joined.mp4
```

## AI Operations

```bash
# Chat mode
max ai chat

# Describe a task and let Max suggest the command
max ai ask "Compress all PDFs in this folder"

# Semantic search
max ai search "query" ./directory

# Generate an image
max ai create "a beautiful sunset" -o sunset.png
```

## File Operations

```bash
# Sort files into folders with AI
max files smart-sort ./downloads

# Find duplicates
max files duplicates ./downloads

# Secure delete
max files shred sensitive.txt

# Back up a file
max files backup report.docx
```

## Background Queue

```bash
max video compress movie.mp4 --queue
max queue status
max queue process
```

## Configuration

```bash
# Show config
max config show

# Check your settings
max config validate

# Export config
max config export -o config.json
```
