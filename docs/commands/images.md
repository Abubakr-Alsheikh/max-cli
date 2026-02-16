# Image Commands

## compress

Compress images to reduce file size.

```bash
max images compress <input> [-q QUALITY] [-o OUTPUT]
```

**Options:**
- `-q, --quality` - Quality (1-100), default: 85
- `-o, --output` - Output file path

## resize

Resize images to specified dimensions.

```bash
max images resize <width>x<height> <input> [-o OUTPUT]
```

**Options:**
- `-o, --output` - Output file path

## convert

Convert images between formats.

```bash
max images convert <input> <output_format> [-o OUTPUT]
```

**Options:**
- `-o, --output` - Output file path

## strip

Remove metadata from images.

```bash
max images strip <input> [-o OUTPUT]
```
