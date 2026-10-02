# Configuration

## Settings

```python
from max_cli.config import settings
```

### Configuration Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| OPENAI_API_KEY | str | None | OpenAI (or OpenRouter, Gemini) API key |
| OPENAI_BASE_URL | str | None | API base URL; empty for OpenAI |
| AI_MODEL | str | gpt-5-nano | Model for ask, chat and analyze |
| AI_IMAGE_MODEL | str | gpt-image-1 | Model for creating and editing images |
| OLLAMA_ENABLED | bool | False | Use a local Ollama model instead |
| OLLAMA_BASE_URL | str | http://localhost:11434 | Where Ollama listens |
| OLLAMA_MODEL | str | llama3 | Ollama model |
| DEFAULT_QUALITY | int | 85 | Image quality for compress and convert |
| MAX_WORKERS | int | 4 | Images processed at once (1-16) |
| DOWNLOAD_TIMEOUT | int | 60 | Seconds a download waits for data before it retries or stops (10 or more): videos, FFmpeg, the noise model, AI images |
| MAX_RETRIES | int | 2 | How many more times the queue runs a task that failed |
| CONFIRM_DESTRUCTIVE | bool | True | Ask before moving, overwriting or deleting files. Off works like `--force` on every command, except `max files shred` |
| GRAB_QUALITY | str | h | Download quality: ss, s, m, h, x |
| GRAB_DEFAULT_TYPE | str | video | video or audio |
| GRAB_DEFAULT_PATH | path | ~/Max Downloads | Where downloads go |
| GRAB_STRIP_PLAYLIST | bool | True | A video link from a playlist gets only that video |
| GRAB_INCLUDE_METADATA | bool | True | Embed title, artist and thumbnail |
| GRAB_MAX_CONCURRENT | int | 3 | Dashboard downloads at once (1-8) |

A value outside its range stops every command with a one-line message naming the setting.

Removed settings (`APP_NAME`, `BATCH_SIZE`, `GRAB_AUDIO_FORMAT`, `GRAB_QUEUE_ENABLED`, `PROGRESS_BAR`, `VERBOSE`) are ignored when a settings file still sets them; `max config validate` names them.

## Configuration Files

Configuration is loaded from (in order):
1. `~/.max_cli/.env` (user-level)
2. `.env` (project-level)

## CLI Commands

```bash
# Show config
max config show

# Set value
max config set MAX_WORKERS 8

# Reset to defaults
max config reset

# Export/Import
max config export config.json
max config import config.json
```
