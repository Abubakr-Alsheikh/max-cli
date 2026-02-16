# Core Modules

## ImageEngine

Image processing operations.

```python
from max_cli.core.image_processor import ImageEngine
```

### Methods

- `compress_image(input_path, output_path, quality=85)` - Compress image
- `resize_image(input_path, output_path, width, height)` - Resize image
- `convert_format(input_path, output_path, format)` - Convert format
- `strip_metadata(input_path, output_path)` - Remove metadata

## PDFEngine

PDF manipulation operations.

```python
from max_cli.core.pdf_engine import PDFEngine
```

### Methods

- `merge_pdfs(input_paths, output_path)` - Merge PDFs
- `split_pdf(input_path, output_dir)` - Split PDF
- `compress_pdf(input_path, output_path, quality)` - Compress PDF
- `ocr_pdf(input_path, output_path, lang)` - OCR extraction

## MediaEngine

Video and audio processing.

```python
from max_cli.core.media_engine import MediaEngine
```

### Methods

- `compress_video(input_path, output_path, quality)` - Compress video
- `extract_audio(input_path, output_path)` - Extract audio
- `convert_format(input_path, output_path, format)` - Convert format
- `trim_video(input_path, output_path, start, end)` - Trim video

## AIEngine

AI-powered features.

```python
from max_cli.core.ai_engine import AIEngine
```

### Methods

- `chat(message)` - Send chat message
- `categorize_files(directory)` - Categorize files
- `semantic_search(query, directory)` - Search files
- `generate_image(prompt)` - Generate image

## FileOrganizer

File management operations.

```python
from max_cli.core.file_organizer import FileOrganizer
```

### Methods

- `scan_directory(directory)` - Scan directory
- `organize_files(directory, rules)` - Organize files
- `find_duplicates(directory)` - Find duplicates
- `secure_delete(path, passes)` - Secure delete
