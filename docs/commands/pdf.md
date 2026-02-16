# PDF Commands

## compress

Compress PDF files to reduce file size.

```bash
max pdf compress <input> [-q QUALITY] [-o OUTPUT]
```

## merge

Merge multiple PDF files into one.

```bash
max pdf merge <file1> <file2> ...
```

## split

Split PDF into separate pages.

```bash
max pdf split <input> [-o OUTPUT_DIR]
```

## ocr

Extract text from PDF using OCR.

```bash
max pdf ocr <input> [-o OUTPUT] [-l LANGUAGE]
```

**Options:**
- `-l, --language` - Language code (eng, spa, fra, etc.)

## watermark

Add watermark to PDF pages.

```bash
max pdf watermark <input> <watermark_image> [-o OUTPUT]
```

## password

Protect PDF with password.

```bash
max pdf password <input> --owner <password> --user <password>
```
