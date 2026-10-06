# Configuration

## Settings

```python
from max_cli.config import settings
```

### Configuration Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| AI_PROVIDER | str | "" | Main AI: openai, openrouter, gemini or ollama. Empty: Ollama when OLLAMA_ENABLED, else openai |
| AI_FALLBACK_PROVIDER | str | "" | Takes over when the main AI fails; empty for none |
| OPENAI_API_KEY | str | None | OpenAI's key, or the key for OPENAI_BASE_URL |
| OPENROUTER_API_KEY | str | None | OpenRouter's key |
| OPENROUTER_MODEL | str | "" | OpenRouter's model; pick one on the Settings page (openrouter/free picks a free model) |
| GEMINI_API_KEY | str | None | Google Gemini's key (free at aistudio.google.com/apikey) |
| GEMINI_MODEL | str | "" | Gemini's model, e.g. gemini-flash-latest (follows Google's newest Flash) |
| OPENAI_BASE_URL | str | None | API base URL for an OpenAI-compatible service; empty for OpenAI. OpenRouter and Gemini use fixed URLs |
| AI_MODEL | str | gpt-6-luna | OpenAI's (or the custom URL's) model |
| AI_IMAGE_MODEL | str | gpt-image-2.5-flare | OpenAI's (or the custom URL's) image model for max ai create and edit |
| OPENROUTER_IMAGE_MODEL | str | "" | OpenRouter's image model; empty for none |
| GEMINI_IMAGE_MODEL | str | "" | Gemini's image model, e.g. gemini-3.1-flash-image; empty for none |
| OLLAMA_ENABLED | bool | False | Older setting: with AI_PROVIDER empty, true means Ollama |
| OLLAMA_BASE_URL | str | http://localhost:11434 | Where Ollama listens |
| OLLAMA_MODEL | str | llama3 | Ollama model |
| DEFAULT_QUALITY | int | 85 | Image quality for compress and convert |
| MAX_WORKERS | int | 4 | Images processed at once (1-16) |
| DOWNLOAD_TIMEOUT | int | 60 | Seconds a download waits for data before it retries or stops (10 or more): videos, FFmpeg, the noise model, AI images |
| MAX_RETRIES | int | 2 | How many more times the queue runs a task that failed (0 or more) |
| CONFIRM_DESTRUCTIVE | bool | True | Ask before moving, overwriting or deleting files. Off works like `--force` on every command, except `max files shred` |
| GRAB_QUALITY | str | h | Download quality: ss (360p), s (480p), m (720p), h (1080p), x (best) |
| GRAB_DEFAULT_TYPE | str | video | video or audio |
| GRAB_DEFAULT_PATH | path | ~/Max Downloads | Where downloads go |
| GRAB_STRIP_PLAYLIST | bool | True | A video link from a playlist gets only that video |
| GRAB_INCLUDE_METADATA | bool | True | Embed title, artist and thumbnail |
| GRAB_MAX_CONCURRENT | int | 3 | Dashboard downloads at once (1-8) |
| DASHBOARD_ICONS | str | auto | Sidebar and launchpad: `auto` (Nerd Font icons when Windows Terminal's font is a Nerd Font, else none), `codes` (a colour bar and the page's key code only), `nerd` (always the icons; needs a Nerd Font) or `emoji` |

A value outside its range stops every command with a one-line message naming the setting.

Removed settings (`APP_NAME`, `BATCH_SIZE`, `GRAB_AUDIO_FORMAT`, `GRAB_QUEUE_ENABLED`, `PROGRESS_BAR`, `VERBOSE`) are ignored when a settings file still sets them; `max config validate` names them.

## Configuration Files

Max reads settings from, in order:
1. `~/.max_config.env` (your global settings)
2. `.env` in the current folder

A setting in the `.env` file wins over the same setting in `~/.max_config.env`, and an environment variable wins over both.

## CLI Commands

```bash
# Show where settings come from and which AI Max uses
max config show

# Pick the main AI and a fallback
max config setup

# Check values and API keys
max config validate

# Delete the config files, so the defaults apply
max config reset

# Export to JSON and import it again
max config export -o config.json
max config import config.json
```

Max has no `config set` command. To change one setting, edit `~/.max_config.env` or use the dashboard's Settings page. See [Config Commands](../commands/config.md).
