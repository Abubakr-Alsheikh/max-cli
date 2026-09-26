# Image Commands

Every `max images` command takes a file or a folder. With no path, it works on the current folder. Max never overwrites your originals:

- For a single file, Max writes `<name>_opt.<ext>` next to it.
- For a folder, Max writes the results to a sibling folder named `<folder>_optimized`. It reads the folder's own images, not those in subfolders.

If an image fails (a damaged file, for example), Max reports it and carries on with the rest. A missing path, a folder with no images, or an unknown `--to` format stops the command with exit code 1.

The dashboard's Tools page has a form for each command, and the Files page's Compress button opens it filled in for the selected image.

All commands process files in parallel. Use `-j` to set the number of workers (default: `MAX_WORKERS` from your config, 4 unless you change it).

## compress

Compress, resize and convert images in one pass.

```bash
max images compress [TARGET] [-q QUALITY] [-s SCALE] [-m MAX_PX] [--jpeg] [--quantize] [--strip | --keep] [-j WORKERS]
```

**Options:**

- `-q` - Quality, 1-100 (default: `DEFAULT_QUALITY` from your config, 85 unless you change it)
- `-s` - Scale as a percentage
- `-m` - Maximum width or height in pixels
- `--jpeg` - Force JPEG output
- `--quantize` - Lossy PNG compression (256 colors)
- `--strip` / `--keep` - Remove or keep EXIF metadata (default: `--strip`)
- `-j` - Number of parallel workers (default: 4)

**Examples:**

```bash
max images compress ./photos
max images compress photo.jpg -q 70
max images compress ./photos -m 1080 --jpeg
```

## resize

Change image dimensions.

```bash
max images resize [TARGET] [-w WIDTH] [-h HEIGHT] [-s SCALE] [-j WORKERS]
```

**Options:**

- `-w` - Width in pixels
- `-h` - Height in pixels
- `-s` - Scale as a percentage
- `-j` - Number of parallel workers (default: 4)

**Examples:**

```bash
max images resize logo.png -w 800
max images resize ./photos -s 50
```

## convert

Convert images to another format.

```bash
max images convert [TARGET] --to FORMAT [-j WORKERS]
```

**Options:**

- `--to` - Target format: `webp`, `jpg` (or `jpeg`) or `png` (required)
- `-j` - Number of parallel workers (default: 4)

**Example:**

```bash
max images convert ./photos --to webp
```

## strip

Remove GPS and EXIF data from images.

```bash
max images strip [TARGET] [-j WORKERS]
```

**Example:**

```bash
max images strip ./photos
```
