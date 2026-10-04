# PDF Commands

Most `max pdf` commands take one PDF and accept `-o` to set the output path. Without `-o`, Max writes a new file next to the input.

A missing input file stops any command with exit code 1. The dashboard's PDF page (`6`) has a form for each command. The AI agent can run every command except `lock`, so it never sees your password.

## Several files at once

`split`, `lock`, `rip`, `ocr`, `form-flatten` and `optimize` also take several PDFs, a folder or a pattern:

```bash
max pdf optimize a.pdf b.pdf             # these two
max pdf ocr ./scans                      # every PDF in the folder
max pdf lock "*.pdf" -p secret           # every PDF here
max pdf ocr ./scans --recursive --queue  # subfolders too, in the background
```

Max runs up to four files at once and lists each as it finishes. A folder gives its PDFs; `--recursive` adds the PDFs in its subfolders (or, with a pattern, the matches in subfolders). Max leaves out hidden files and folders.

With a folder or a pattern, Max skips PDFs whose result is already there (`a.pdf` when `a_optimized.pdf` exists) and never treats its own earlier results as new input. `--redo` runs those files again. Files you name one by one always run. Put a pattern in quotes: if your shell expands it first, Max sees named files and runs them all. `split` has no single result name to check, so it has no `--redo` and runs every PDF it finds.

`-o` works only with one file, and Max refuses it with several. Then each result goes next to its file. If a file fails, Max carries on with the rest, lists the failures at the end and exits with code 1.

`stamp` takes one PDF, because its text comes right after the file name. `merge`, `bundle` and `compress` read a folder in their own way, described below.

## merge

Combine several PDFs into one.

```bash
max pdf merge [INPUTS]... [--output OUTPUT]
```

**Options:**

- `--output`, `-o` - Output file

`INPUTS` is a list of files or a single folder. With no inputs, Max merges the PDFs in the current folder. Without `--output`, Max names the result `<first file>_merged.pdf`, or `<folder>_merged.pdf` inside the folder. Max leaves an earlier merge result out of the inputs, so running the command twice gives the same file.

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

`INPUTS` is a list of files or a folder (default: the current folder). Without `--output`, Max writes `<folder>_bundled.pdf` next to the folder, or `<first file>_bundled.pdf` next to the first file. With `--no-compress`, the name ends in `_merged.pdf`.

**Options:**

- `--output`, `-o` - Final output path. A folder works too: Max saves the default name inside it.
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

For a single file, Max writes `<name>_compressed.pdf`. For a folder, Max compresses the PDFs in it (not those in subfolders) and writes the results, under their own names, into a `compressed/` subfolder.

## split

Keep a page range, remove a page range, or split into chunks.

```bash
max pdf split TARGET... [--start N] [--end N] [--chunks N] [--remove] [--list] [-o OUTPUT] [--recursive]
```

**Options:**

- `--start`, `-s` - First page, 1-based (default: 1)
- `--end`, `-e` - Last page; `-1` means the last page (default: -1)
- `--chunks`, `-c` - Split into files of N pages each (default: 0, off)
- `--remove` - Remove the range instead of keeping it
- `--list` - Print the page count and exit
- `-o` - Output file (one PDF only)
- `--recursive` - With a folder or pattern, look in subfolders too

Without `-o`, Max writes `<name>_p<start>-<end>.pdf`, or `<name>_without_p<start>-<end>.pdf` with `--remove`. Chunks go next to the PDF as `<name>_p1-10.pdf`, `<name>_p11-20.pdf` and so on; pass a folder to `-o` to put them there instead.

**Examples:**

```bash
max pdf split file.pdf -s 1 -e 10       # Keep pages 1-10
max pdf split file.pdf -s 11            # Keep page 11 to the end
max pdf split file.pdf -e 5             # Keep pages 1-5
max pdf split file.pdf -c 10            # Chunks of 10 pages
max pdf split file.pdf --remove -s 5 -e 10
max pdf split ./reports -s 1 -e 1       # First page of every PDF in the folder
```

## stamp

Print a text watermark across the center of every page.

```bash
max pdf stamp TARGET [TEXT] [-o OUTPUT]
```

`TEXT` defaults to `DRAFT`. Without `-o`, Max writes `<name>_stamped.pdf`. `stamp` takes one PDF at a time.

**Options:**

- `-o` - Output file

**Example:**

```bash
max pdf stamp report.pdf "CONFIDENTIAL"
```

## lock

Encrypt a PDF with a password.

```bash
max pdf lock TARGET... --password PASSWORD [-o OUTPUT] [--recursive] [--redo]
```

**Options:**

- `--password`, `-p` - Password (required)
- `-o` - Output file (default: `<name>_locked.pdf`; one PDF only)
- `--recursive` - With a folder or pattern, look in subfolders too
- `--redo` - With a folder or pattern, also lock PDFs that have a `_locked.pdf` already

**Example:**

```bash
max pdf lock ./invoices -p secret
```

## rip

Extract every image inside a PDF.

```bash
max pdf rip TARGET... [-o FOLDER] [--recursive] [--redo]
```

**Options:**

- `-o` - Folder for the images (default: `<name>_assets/`). One PDF only: Max names the images by page (`page1_img1.png`), so it refuses `-o` with several PDFs rather than let them overwrite each other's images.
- `--recursive` - With a folder or pattern, look in subfolders too
- `--redo` - With a folder or pattern, also rip PDFs that have an `_assets/` folder already

## ocr

Extract text from a scanned PDF with OCR.

```bash
max pdf ocr TARGET... [--lang LANG] [-o OUTPUT] [--recursive] [--redo] [--queue]
```

**Options:**

- `--lang`, `-l` - Tesseract language code, such as `eng`, `deu`, `fra` or `eng+deu` (default: `eng`)
- `-o` - Output text file (default: `<name>.txt`; one PDF only)
- `--recursive` - With a folder or pattern, look in subfolders too
- `--redo` - With a folder or pattern, also read PDFs that have a `.txt` already
- `--queue` - Run in the background, one job per PDF. `max queue status` shows progress.

OCR needs the Tesseract program and the `ocr` extra:

```bash
pip install max-cli[ocr]
```

**Examples:**

```bash
max pdf ocr scan.pdf -l deu
max pdf ocr ./scans --queue
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
max pdf form-flatten TARGET... [-o OUTPUT] [--recursive] [--redo]
```

**Options:**

- `-o` - Output file (default: `<name>_flattened.pdf`; one PDF only)
- `--recursive` - With a folder or pattern, look in subfolders too
- `--redo` - With a folder or pattern, also flatten PDFs that have a `_flattened.pdf` already

## optimize

Remove unused objects, compress images and linearize the file for fast web viewing.

```bash
max pdf optimize TARGET... [-o OUTPUT] [--no-compress] [--no-linearize] [--recursive] [--redo]
```

**Options:**

- `-o` - Output file (default: `<name>_optimized.pdf`; one PDF only)
- `--no-compress` - Skip image compression
- `--no-linearize` - Skip web optimization
- `--recursive` - With a folder or pattern, look in subfolders too
- `--redo` - With a folder or pattern, also optimize PDFs that have an `_optimized.pdf` already

**Example:**

```bash
max pdf optimize "*.pdf" --recursive
```

## compare

Compare two PDFs. Max reports a different page count and lists each page whose text differs.

```bash
max pdf compare FILE1 FILE2
```
