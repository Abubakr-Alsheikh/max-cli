# Max CLI

[![PyPI Version](https://img.shields.io/pypi/v/max-cli.svg)](https://pypi.org/project/max-cli/)
[![Python Version](https://img.shields.io/pypi/pyversions/max-cli.svg)](https://pypi.org/project/max-cli/)
[![License](https://img.shields.io/pypi/l/max-cli.svg)](https://github.com/Abubakr-Alsheikh/max-cli/blob/main/LICENSE)
[![Build Status](https://github.com/Abubakr-Alsheikh/max-cli/actions/workflows/ci.yml/badge.svg)](https://github.com/Abubakr-Alsheikh/max-cli/actions)
[![Documentation](https://img.shields.io/badge/docs-MkDocs-blue)](https://Abubakr-Alsheikh.github.io/max-cli/)

**Your lazy, fast terminal assistant.** Max turns jobs like compressing a video, merging PDFs or downloading from YouTube into short commands you can remember.

```bash
max video compress ~/Videos --recursive      # every video in a folder tree, side by side
max pdf ocr scans/ --queue                   # OCR in the background; close the terminal if you like
max "sort my Music folder by artist"          # or say it in plain words and let the AI agent do it
max                                           # or open the dashboard
```

**Full documentation:** https://Abubakr-Alsheikh.github.io/max-cli/

## Contents

- [What Max does](#what-max-does)
- [Install](#install)
- [Three ways to use Max](#three-ways-to-use-max)
- [Command groups](#command-groups)
- [Several files at once](#several-files-at-once)
- [Background jobs](#background-jobs)
- [The AI agent](#the-ai-agent)
- [The dashboard](#the-dashboard)
- [Safety: confirm, undo, back up](#safety-confirm-undo-back-up)
- [Configuration](#configuration)
- [Command cheat sheets](#command-cheat-sheets)
- [Troubleshooting](#troubleshooting)
- [For developers](#for-developers)

## What Max does

- **Video and audio:** compress, cut, convert, make GIFs, fix volume and noise, edit music tags, sort songs into folders. Max downloads FFmpeg for you the first time you need it.
- **PDF:** merge, split, compress, OCR, watermark, lock, fill and flatten forms, compare.
- **Images:** compress, resize, convert, strip GPS and camera data.
- **Downloads:** video or audio from YouTube and most other sites, with quality presets and a queue.
- **Files:** sort by meaning with AI, number files, find duplicates, back up, shred, and undo.
- **AI:** an agent that runs Max's own commands for you, plus image analysis, image generation, search by meaning and data extraction.
- **Batches and a background queue:** point a command at a folder or a pattern, and send long jobs to a worker that keeps going after you close the terminal.
- **A dashboard:** every command as a form, live progress, history, undo and settings in one terminal app.

## Install

You need Python 3.9 or newer.

```bash
pip install max-cli
```

For the newest code, install from the repository:

```bash
git clone https://github.com/Abubakr-Alsheikh/max-cli.git
cd max-cli
pip install -e .
```

**FFmpeg** (video and audio): Max looks on your PATH first. Without it, the first video or audio command offers to download a copy into `~/.max_cli/bin/`. To do it ahead of time, run `max config setup-ffmpeg`, or use your package manager (`winget install Gyan.FFmpeg`, `brew install ffmpeg`, `sudo apt install ffmpeg`).

**OCR** (optional): install [Tesseract](https://github.com/tesseract-ocr/tesseract), then `pip install max-cli[ocr]`.

**AI** (optional): run `max config setup` and pick a main AI and a fallback. Max switches to the fallback when the main one fails.

| Provider | Key | Good for |
|----------|-----|----------|
| [OpenRouter](https://openrouter.ai/keys) | Yes | Many models behind one key, including free ones |
| [Google Gemini](https://aistudio.google.com/app/apikey) | Yes | A free tier, vision and image generation |
| [OpenAI](https://platform.openai.com/api-keys) | Yes | GPT models, image generation, or any server that speaks the OpenAI API |
| [Ollama](https://ollama.com) | No | Private AI on your own machine, no internet |

Check the install with `max --version`.

## Three ways to use Max

**1. Commands.** Each job is `max <group> <command>`. Run `max <group> --help` to see a group's commands.

```bash
max video compress movie.mp4
max pdf merge a.pdf b.pdf -o both.pdf
max grab download "https://youtube.com/watch?v=..." -a
```

**2. The AI agent.** Say what you want. The agent plans the steps, runs Max's commands and asks before it changes or deletes files.

```bash
max "convert every m4a in this folder to mp3"
max ai chat
```

**3. The dashboard.** Type `max` on its own. Each command group has a page with forms, live progress and history.

## Command groups

| Group | What it does | Example | Docs |
|-------|--------------|---------|------|
| `max video` | Compress, convert, cut, GIF, volume, noise, color, stabilize, record, stream | `max video compress movie.mp4` | [Video](docs/commands/media.md) |
| `max audio` | Tags, compress, denoise, sort songs into folders | `max audio organize "*.mp3" --pattern artist` | [Audio](docs/commands/audio.md) |
| `max images` | Compress, resize, convert, strip metadata | `max images compress ./photos` | [Images](docs/commands/images.md) |
| `max pdf` | Merge, split, compress, OCR, stamp, lock, forms, compare | `max pdf bundle contracts/` | [PDF](docs/commands/pdf.md) |
| `max grab` | Download video or audio from YouTube and other sites | `max grab download URL -q h` | [Download](docs/commands/grab.md) |
| `max files` | Smart sort, rename, duplicates, backups, shred, undo | `max files smart-sort ~/Downloads` | [Files](docs/commands/files.md) |
| `max ai` | The agent, plus vision, image generation, search, extraction | `max ai ask "merge the PDFs here"` | [AI](docs/commands/ai.md) |
| `max queue` | Watch and control background jobs | `max queue status` | [Queue](docs/commands/queue.md) |
| `max tools` | QR code for a link, clipboard helpers | `max tools share http://192.168.1.20:8000` | [Tools](docs/commands/tools.md) |
| `max config` | AI keys, defaults, FFmpeg | `max config setup` | [Config](docs/commands/config.md) |
| `max dashboard` | The terminal dashboard (a bare `max` opens it too) | `max` | [Dashboard](docs/commands/dashboard.md) |
| `max plugins` | List, inspect, enable and disable plugins | `max plugins list` | [Plugins](#plugins) |

## Several files at once

Commands that work on one file also take several files, a folder or a pattern. Max runs the files side by side and prints one summary.

```bash
max video compress clip1.mp4 clip2.mp4
max video audio-convert "*.m4a" --format mp3
max audio compress ~/Music --recursive        # look in subfolders too
max pdf ocr scans/ --redo                     # redo files that already have a result
```

- A folder or a pattern skips files whose result already exists, and skips Max's own results (so `compress` doesn't compress `movie_compressed.mp4`). Add `--redo` to run them anyway. Files you name always run.
- Max asks once before it overwrites anything, not once per file.
- Two files whose results would share a name (`clip.mov` and `clip.mp4` both make `clip_compressed.mp4`) don't both run: Max runs the first and names the others.
- If one file fails, the others still run, and the command exits with code 1.

These commands take batches: every `max video` command except `concat`, `record`, `stream` and `preview`; `max audio compress`, `denoise` and `clear`; `max pdf split`, `lock`, `rip`, `ocr`, `form-flatten` and `optimize`; `max files backup`. `max images` commands took folders already. `max files shred` and `max pdf stamp` take one file on purpose.

## Background jobs

Add `--queue` to a long job and Max puts it in the queue, then starts a background worker. The worker keeps running after you close the terminal and stops when the queue is empty.

```bash
max video compress ~/Videos --queue     # one job per video
max grab download URL --queue
max queue status                        # what's waiting, running and done
max queue cancel <task-id>
max queue retry <task-id>
```

`--queue` works on the video batch commands except `snap`, on `max audio compress` and `denoise`, `max pdf ocr` and `max grab download`. The dashboard, the CLI and the worker share one queue, so a job you add in one shows up in the others. If the worker crashes, the next one puts its unfinished jobs back in line. `max queue process` runs the queue in your terminal instead. See [Queue](docs/commands/queue.md).

## The AI agent

```bash
max "shrink every video in this folder"
max ai ask "merge the PDFs in Downloads into one file"
max "sort my Music folder into Artist/Album folders" --dry-run   # show the plan, change nothing
max ai chat                                                    # it remembers the conversation
```

The agent uses Max's own commands and nothing else: it can't run other programs. It looks first (lists folders, reads file details, finds files by kind, size or age), then acts. It runs a batch over many files in one step, skips files that already have a result, and runs independent actions in parallel. From the CLI it sends long jobs (video and audio work, OCR, downloads) to the background queue.

It stays inside the current folder, folders you name and your download folder. It asks before it moves, overwrites or deletes files, whatever `CONFIRM_DESTRUCTIVE` says. Each request has a limit on steps, actions and tokens. The dashboard's AI page runs the same agent. See [AI](docs/commands/ai.md).

## The dashboard

Type `max` (or `max dashboard`). In a script or a pipe, a bare `max` prints the help instead.

| Key | Page | What you do there |
|-----|------|-------------------|
| `1` | Home | Ask Max in plain words, jump to a tool page, rerun the actions you use most, see your week and recent activity |
| `2` | Download | Paste a link, preview it, pick a quality, watch progress |
| `3` | Video | Pick a video (or a folder), see what it holds, run any video action |
| `4` | Audio | See and edit tags, sort music into folders, compress or clean audio |
| `5` | Images | See pixels, date, camera and GPS; compress, resize, convert, strip |
| `6` | PDF | See pages and whether a PDF is locked or scanned; run any PDF action |
| `7` | Files | See a folder's files by kind and size; sort, clean, back up |
| `8` | AI | Talk to the agent and watch each action it runs |
| `9` | Activity | The queue (pause, cancel, retry), the history of every action, and undo |
| `0` | Extras | QR code for a link, save a clipboard image, copy a text file |
| `,` | Settings | AI providers and models, defaults, safety, FFmpeg, page icons |

Forms take a file, a folder or a pattern, with **subfolders** and **redo** checkboxes for batches. Queueable forms can send the work to the queue. Other keys: `Ctrl+P` finds any action by name, `J` opens the jobs window, `?` shows help, `Ctrl+B` folds the sidebar to icons, `q` quits.

Each page keeps one colour across the sidebar, the launchpad and Home's charts. With a [Nerd Font](https://www.nerdfonts.com/) in your terminal, set **Page icons** to **Nerd Font** in Settings for crisper icons. See [Dashboard](docs/commands/dashboard.md).

## Safety: confirm, undo, back up

- **Confirm:** Max asks before a command moves, overwrites or deletes files. `--force` skips the question, and `CONFIRM_DESTRUCTIVE=false` turns the questions off. `max files shred` asks either way.
- **Undo:** `max files undo` reverses the last `order`, `smart-sort`, `duplicates --delete` or `audio organize`. `max files history` lists what you can undo.
- **Backups:** `duplicates --delete` saves a backup before it deletes. `max files backup` and `max files backups --restore` do it by hand.
- **No undo for shred:** `max files shred` overwrites the file before it deletes it, and keeps no copy.
- **Exit codes:** `0` when a command worked, `1` when it reported an error (even one failed file in a batch), `2` for a usage mistake such as a bad option.

## Configuration

`max config setup` covers the AI. `max config grab` sets your download defaults. The dashboard's Settings page (`,`) shows everything else.

Max reads settings from two files. A `.env` in the current folder overrides `~/.max_config.env`.

```ini
# Main AI and a fallback: openai, openrouter, gemini or ollama
AI_PROVIDER=openrouter
OPENROUTER_API_KEY=sk-or-...
OPENROUTER_MODEL=openrouter/free
AI_FALLBACK_PROVIDER=gemini
GEMINI_API_KEY=AIza...
GEMINI_MODEL=gemini-2.5-flash

# Defaults
DEFAULT_QUALITY=80          # image quality
GRAB_QUALITY=h              # ss, s, m, h or x
GRAB_DEFAULT_PATH=~/Max Downloads

# Safety and network
CONFIRM_DESTRUCTIVE=true    # false skips "Are you sure?" (shred still asks)
MAX_RETRIES=2               # reruns of a failed queued task
```

```bash
max config show       # where each setting comes from
max config validate   # check your settings
max config export     # save to JSON (keys left out unless you add --include-secrets)
```

Every setting is listed in [Config settings](docs/api/config.md).

## Command cheat sheets

Click a group to open its examples. Each group's docs page lists every option.

<details>
<summary><b>Video</b> (<code>max video</code>)</summary>

```bash
max video compress video.mp4                 # balanced (CRF 28)
max video compress video.mp4 --level high    # better quality, bigger file (CRF 23)
max video compress video.mp4 --level max     # smallest file (CRF 35)
max video convert video.mkv --format mp4
max video to-audio lecture.mp4               # MP3, 192k
max video to-audio lecture.mp4 --format wav
max video cut movie.mp4 --start 0:30 --end 1:00
max video cut movie.mp4 --start 0 --duration 30
max video gif clip.mp4
max video snap video.mp4 --time 1:30         # screenshot
max video louder quiet.mp4 --db 10
max video mute video.mp4
max video denoise recording.mp4
max video concat "*.mp4" -o all.mp4          # --method fast|safe
max video audio-convert song.wav --format mp3
```

Also: `brightness`, `color`, `stabilize`, `normalize`, `record`, `stream` and `preview`. See [Video](docs/commands/media.md).
</details>

<details>
<summary><b>Audio</b> (<code>max audio</code>)</summary>

```bash
max audio get song.mp3
max audio set song.mp3 --artist "Artist" --album "Album"
max audio batch "folder/*.mp3" --album "My Album" --artist "Band"
max audio organize "*.mp3" --pattern artist
max audio compress recording.wav
max audio denoise podcast.mp3
max audio clear song.mp3                     # remove every tag
```
</details>

<details>
<summary><b>PDF</b> (<code>max pdf</code>)</summary>

```bash
max pdf merge a.pdf b.pdf -o both.pdf
max pdf bundle contracts/                    # merge a folder, then compress
max pdf split document.pdf -s 1 -e 5         # keep pages 1-5
max pdf split document.pdf --remove -s 5 -e 10
max pdf split document.pdf -c 10             # files of 10 pages
max pdf compress large.pdf --dpi 100 --quality 60
max pdf stamp document.pdf "CONFIDENTIAL"
max pdf lock document.pdf --password "s3cret"
max pdf ocr scan.pdf --lang eng+deu          # writes scan.txt
max pdf rip brochure.pdf                     # pull out the images
max pdf form-data form.pdf
max pdf form-fill form.pdf -f name="John" -f email="john@example.com"
max pdf form-flatten form_filled.pdf
max pdf optimize document.pdf
max pdf compare old.pdf new.pdf
```
</details>

<details>
<summary><b>Images</b> (<code>max images</code>)</summary>

```bash
max images compress ./photos                 # results go to photos_optimized/
max images compress photo.jpg -q 70
max images compress ./photos -m 1080         # longest side 1080px
max images resize logo.png -w 800
max images resize photo.png -s 50            # half size
max images convert photo.jpg --to webp
max images strip ./photos                    # remove GPS and camera data
```
</details>

<details>
<summary><b>Downloads</b> (<code>max grab</code>)</summary>

```bash
max grab download URL                        # video, best quality
max grab download URL -a                     # audio only
max grab download URL -q h                   # ss=360p s=480p m=720p h=1080p x=4K
max grab download URL -o ./my-videos
max grab download                            # interactive: paste links one by one
max grab queue                               # pending downloads
max grab history
max grab pot-setup                           # fix YouTube HTTP 403 errors (once)
max config grab                              # save your defaults
```

| Quality | Video | Audio |
|---------|-------|-------|
| `ss` | 360p | 64 kbps |
| `s` | 480p | 64 kbps |
| `m` | 720p | 128 kbps |
| `h` | 1080p | 192 kbps |
| `x` | 4K | 320 kbps |
</details>

<details>
<summary><b>Files</b> (<code>max files</code>)</summary>

```bash
max files smart-sort ./downloads             # AI sorts files into folders
max files order ./photos                     # 1_file, 2_file, ...
max files duplicates ./downloads -r          # list duplicates
max files duplicates ./downloads -r --delete # keep one copy (asks first)
max files preview notes.md
max files shred secrets.txt -p 7             # asks first, can't be undone
max files backup report.docx
max files backups --restore <backup-path>
max files backup-cleanup --days 30
max files undo
max files history -v
```
</details>

<details>
<summary><b>AI</b> (<code>max ai</code>)</summary>

```bash
max ai ask "merge the PDFs in Downloads"
max ai chat
max ai analyze screenshot.png -p "What error is shown?"
max ai create "A cat on a bike" -o cat.png
max ai edit photo.jpg "Add a sunset background" -o new.jpg
max ai search "notes about the Q3 budget" ./notes --ext md,txt
max ai extract receipt.jpg -s "total:Total amount" -s "date:Date" -o receipt.json
```
</details>

<details>
<summary><b>Queue, tools and config</b></summary>

```bash
max queue status
max queue start                              # start the worker for jobs left from earlier
max queue process --max 3                    # run jobs here instead
max queue stats
max queue history --type download
max queue clear --failed

max tools share "https://example.com"        # QR code in the terminal
max tools paste screenshot.png               # save the clipboard image
max tools copy notes.txt                     # copy a text file to the clipboard

max config show
max config save                              # make this folder's .env your global settings
max config reset --local
max config import cfg.json
```
</details>

## Troubleshooting

- **"FFmpeg not found":** run `max config setup-ffmpeg`, or accept the download offer the next time you run a video or audio command.
- **"The AI isn't set up":** run `max config setup`, or open Settings in the dashboard.
- **YouTube HTTP 403:** run `max grab pot-setup` once, or try `--player-client web`.
- **A queued job doesn't start:** run `max queue status` to see the worker, then `max queue start`.
- **Something else:** check `pip show max-cli` for your version and [open an issue](https://github.com/Abubakr-Alsheikh/max-cli/issues).

## For developers

```bash
git clone https://github.com/Abubakr-Alsheikh/max-cli.git
cd max-cli
pip install -e .[dev]

pytest                                # tests
ruff check . && ruff format .         # lint and format
python scripts/mypy_baseline.py       # type errors may not rise above the baseline
python scripts/ci_local.py --full     # the GitHub CI checks, on Python 3.9 to 3.12
```

### How the code fits together

```text
src/max_cli/
├── core/
│   ├── catalog/      # one description per action: params, defaults, danger, batches
│   ├── operations/   # the work behind each action; returns an ActionResult
│   ├── engines/      # FFmpeg, PDF, images, AI providers, downloads, the task queue
│   ├── agent/        # the AI agent: tools, path scope, parallel and batch runs
│   └── cli/          # lazy command-group loading
├── interface/        # Typer commands (cli_*.py) and the Textual dashboard (tui/)
├── common/           # shared helpers: atomic writes, file locks, undo log, activity log
├── plugins/          # plugin base classes and loader
└── config.py         # settings (pydantic)
```

The CLI, the dashboard and the agent read the same catalog and run the same operations, so they offer the same options. [AGENTS.md](AGENTS.md) explains the patterns and rules, and [Contributing](docs/contributing.md) covers the workflow.

### Plugins

Max loads plugins from `~/.max_cli/plugins/`, and from folders listed under `"plugin_dirs"` in `~/.max_cli/plugins.json`. It never loads plugins from the current folder, so a cloned repository can't run code just because you ran `max` inside it.

```bash
max plugins list --all
max plugins info <plugin-name>
max plugins enable <plugin-name>
max plugins disable <plugin-name>
```

A plugin is a module that defines a `CLIPlugin` subclass and creates one instance named `plugin`:

```python
import typer

from max_cli.plugins.base import CLIPlugin


class HelloPlugin(CLIPlugin):
    def __init__(self) -> None:
        super().__init__(name="hello", version="1.0.0", description="Say hello")

    def register(self, app: typer.Typer) -> None:
        @app.command("hello")
        def hello(name: str = typer.Option("World", "--name", "-n")) -> None:
            """Say hello."""
            typer.echo(f"Hello, {name}!")


plugin = HelloPlugin()
```

See `examples/plugins/hello_world.py` and `PLANS/docs/plugins.md` for the hooks (`validate`, `on_load`, `on_unload`, `priority`).

## Contributing

Bug reports and pull requests are welcome. Open an [issue](https://github.com/Abubakr-Alsheikh/max-cli/issues) first for anything large, then see [Contributing](docs/contributing.md).

## License

MIT. Use it, change it, share it.
