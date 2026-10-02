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
| GEMINI_MODEL | str | "" | Gemini's model, e.g. gemini-2.5-flash |
| OPENAI_BASE_URL | str | None | API base URL; empty for OpenAI |
| AI_MODEL | str | gpt-5-nano | OpenAI's (or the custom URL's) model |
| AI_IMAGE_MODEL | str | gpt-image-1 | Model for creating and editing images |
| OLLAMA_ENABLED | bool | False | Older setting: with AI_PROVIDER empty, true means Ollama |
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
