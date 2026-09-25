# Tools Commands

The `max tools` group holds small system utilities for QR codes and the clipboard.

## share

Print a QR code in your terminal. Scan it with your phone to open a URL, such as a local dev server, without typing it.

```bash
max tools share DATA
```

`DATA` is the text or URL to encode.

**Example:**

```bash
max tools share "http://192.168.1.20:8000"
```

## copy

Copy the contents of a text file to your system clipboard. Max refuses binary files.

```bash
max tools copy TARGET
```

**Example:**

```bash
max tools copy notes.txt
```

On Linux, the clipboard needs `xclip`, `xsel` or `wl-clipboard` installed.

## paste

Save the image on your clipboard to a file. Use it right after you take a screenshot.

```bash
max tools paste [OUTPUT]
```

`OUTPUT` defaults to `clipboard.png`. If you leave off the extension, Max adds `.png`. Max replaces a file that already has that name.

**Examples:**

```bash
max tools paste
max tools paste bug-report
```

The second example saves `bug-report.png`. If the clipboard holds text or files instead of an image, Max tells you and saves nothing.
