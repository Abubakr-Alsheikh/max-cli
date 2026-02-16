# Configuration

## Settings

```python
from max_cli.config import settings
```

### Configuration Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| OPENAI_API_KEY | str | None | OpenAI API key |
| OPENAI_BASE_URL | str | https://api.openai.com/v1 | API base URL |
| AI_MODEL | str | gpt-4 | Default AI model |
| AI_IMAGE_MODEL | str | dall-e-3 | Image generation model |
| MAX_WORKERS | int | 4 | Max parallel workers |
| BATCH_SIZE | int | 10 | Batch processing size |
| DOWNLOAD_TIMEOUT | int | 300 | Download timeout (seconds) |
| MAX_RETRIES | int | 3 | Max retry attempts |
| PROGRESS_BAR | bool | True | Show progress bars |
| VERBOSE | bool | False | Verbose output |
| CONFIRM_DESTRUCTIVE | bool | True | Confirm destructive operations |

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
