# Installation

## Prerequisites

- Python 3.9 or newer (uv, below, installs it for you)
- FFmpeg for video and audio commands (Max can download it for you)
- Tesseract, only for `max pdf ocr`

New to the terminal? Follow [Start here](start-here.md) instead: it walks through every step.

## Install

The quickest way is the one-line installer. It installs [uv](https://docs.astral.sh/uv/) when you don't have it (uv brings its own Python), then Max, and checks that Max starts. Run it again any time to update.

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://raw.githubusercontent.com/Abubakr-Alsheikh/max-cli/main/install.ps1 | iex"   # Windows
```

```bash
curl -LsSf https://raw.githubusercontent.com/Abubakr-Alsheikh/max-cli/main/install.sh | sh   # macOS and Linux
```

Or run the steps yourself with [uv](https://docs.astral.sh/uv/):

```bash
uv tool install max-cli     # update later with: max update
```

Install uv first with `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"` (Windows) or `curl -LsSf https://astral.sh/uv/install.sh | sh` (macOS and Linux), then open a new terminal.

With Python already installed, `pipx install max-cli` works the same way. Plain pip works too, best inside a virtual environment:

```bash
pip install max-cli
```

For the newest code, install from the repository:

```bash
git clone https://github.com/Abubakr-Alsheikh/max-cli.git
cd max-cli
pip install -e .
```

For development, add the `dev` extra: `pip install -e .[dev]`.

The base install includes the AI, PDF, image and download features and the dashboard.

## Optional extras

| Extra | What it adds |
|-------|--------------|
| `ocr` | `pytesseract`, for `max pdf ocr`. Install [Tesseract](https://github.com/tesseract-ocr/tesseract) too |
| `dev` | pytest, ruff, mypy and mkdocs |
| `tui` | Nothing. It stays so `pip install max-cli[tui]` from older instructions still works |

## FFmpeg

Max looks for FFmpeg on your PATH. If it can't find it, the first video or audio command offers to download a build for your platform into `~/.max_cli/bin/`, and checks that it runs.

To install it ahead of time:

```bash
max config setup-ffmpeg
```

Or use your package manager: `winget install Gyan.FFmpeg` (Windows), `brew install ffmpeg` (macOS), `sudo apt install ffmpeg` (Debian and Ubuntu).

## AI provider

The AI agent and the `max ai` commands need a provider. Run the wizard:

```bash
max config setup
```

It asks for a main AI and a fallback, each with its key and model. Max switches to the fallback when the main one fails.

| Provider | Key | Good for |
|----------|-----|----------|
| [OpenRouter](https://openrouter.ai/keys) | Yes | Many models behind one key, including free ones |
| [Google Gemini](https://aistudio.google.com/app/apikey) | Yes | A free tier, vision and image generation |
| [OpenAI](https://platform.openai.com/api-keys) | Yes | GPT models, or any server that speaks the OpenAI API |
| [Ollama](https://ollama.com) | No | Private AI on your own machine |

You can also set the providers on the dashboard's Settings page, which lists each provider's models for you to pick.

## Check the install

```bash
max --version
max doctor        # FFmpeg, the AI, YouTube, folders: each with its fix
```

## Update

```bash
max update
```

Max updates itself the way you installed it (uv, pipx or pip) and tells you when a new version is out. See [Update and Doctor](commands/update.md).
