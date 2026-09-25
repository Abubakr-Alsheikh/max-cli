# PDF Commands

Most `max pdf` commands take one PDF and accept `-o` to set the output path. Without `-o`, Max writes a new file next to the input.

## merge

Combine several PDFs into one.

```bash
max pdf merge [INPUTS]... [--output OUTPUT]
```

`INPUTS` is a list of files or a single folder. Without `--output`, Max names the result `<first file>_merged.pdf`, or `<folder>_merged.pdf` inside the folder.

**Examples:**

```bash
max pdf merge part1.pdf part2.pdf -o full.pdf
max pdf merge ./contracts
```

## bundle

Merge files, then compress the result. With `--no-compress`, it only merges.

```bash
max pdf bundle [INPUTS]... [--output OUTPUT] [--dpi DPI] [--quality Q] [--no-compress]
```

**Options:**

- `--output`, `-o` - Final output path
- `--dpi`, `-d` - Compression DPI (default: 150)
- `--quality`, `-q` - JPEG quality, 1-100 (default: 80)
- `--no-compress` - Merge only

**Examples:**

```bash
max pdf bundle ./contracts
max pdf bundle a.pdf b.pdf --no-compress
max pdf bundle -d 72 -q 50
```

## compress

Shrink a PDF, or every PDF in a folder.

```bash
max pdf compress TARGET [--dpi DPI] [--quality Q]
```

**Options:**

- `--dpi`, `-d` - Image resolution. Lower means a smaller file (default: 150)
- `--quality`, `-q` - JPEG quality, 1-100. Lower means a smaller file (default: 80)

For a single file, Max writes `<name>_compressed.pdf`. For a folder, Max writes the results into a `compressed/` subfolder.

## split

Keep a page range, remove a page range, or split into chunks.

```bash
max pdf split TARGET [--start N] [--end N] [--chunks N] [--remove] [--list] [-o OUTPUT]
```

**Options:**

- `--start`, `-s` - First page, 1-based (default: 1)
- `--end`, `-e` - Last page; `-1` means the last page (default: -1)
- `--chunks`, `-c` - Split into files of N pages each (default: 0, off)
- `--remove` - Remove the range instead of keeping it
- `--list` - Print the page count and exit
- `-o` - Output file

**Examples:**

```bash
max pdf split file.pdf -s 1 -e 10       # Keep pages 1-10
max pdf split file.pdf -s 11            # Keep page 11 to the end
max pdf split file.pdf -c 10            # Chunks of 10 pages
max pdf split file.pdf --remove -s 5 -e 10
```

## stamp

Print a text watermark across the center of every page.

```bash
max pdf stamp TARGET [TEXT] [-o OUTPUT]
```

`TEXT` defaults to `DRAFT`.

**Example:**

```bash
max pdf stamp report.pdf "CONFIDENTIAL"
```

## lock

Encrypt a PDF with a password.

```bash
max pdf lock TARGET --password PASSWORD [-o OUTPUT]
```

**Options:**

- `--password`, `-p` - Password (required)
- `-o` - Output file

## rip

Extract every image inside a PDF.

```bash
max pdf rip TARGET [-o FOLDER]
```

Without `-o`, Max saves the images to `<name>_assets/`.

## ocr

Extract text from a scanned PDF with OCR.

```bash
max pdf ocr TARGET [--lang LANG] [-o OUTPUT]
```

**Options:**

- `--lang`, `-l` - Tesseract language code, such as `eng`, `deu`, `fra` or `eng+deu` (default: `eng`)
- `-o` - Output text file (default: `<name>.txt`)

OCR needs the Tesseract program and the `ocr` extra:

```bash
pip install max-cli[ocr]
```

## form-data

Print the field names and values of a PDF form.

```bash
max pdf form-data TARGET
```

## form-fill

Fill PDF form fields. Repeat `--field` for each field.

```bash
max pdf form-fill TARGET --field NAME=VALUE [--field NAME=VALUE ...] [-o OUTPUT]
```

**Options:**

- `--field`, `-f` - `name=value` pair (required, repeatable)
- `-o` - Output file (default: `<name>_filled.pdf`)

**Example:**

```bash
max pdf form-data form.pdf
max pdf form-fill form.pdf -f name="John" -f email="john@example.com"
```

## form-flatten

Turn form fields into regular page content so nobody can edit them.

```bash
max pdf form-flatten TARGET [-o OUTPUT]
```

Without `-o`, Max writes `<name>_flattened.pdf`.

## optimize

Remove unused objects, compress images and linearize the file for fast web viewing.

```bash
max pdf optimize TARGET [-o OUTPUT] [--no-compress] [--no-linearize]
```

**Options:**

- `-o` - Output file (default: `<name>_optimized.pdf`)
- `--no-compress` - Skip image compression
- `--no-linearize` - Skip web optimization

## compare

Compare two PDFs. Max reports a different page count and lists each page whose text differs.

```bash
max pdf compare FILE1 FILE2
```
