# Config Commands

## setup

Interactive wizard to configure AI providers and models.

```bash
max config setup
```

This wizard will guide you through:

- Choosing your AI provider (Google Gemini, OpenAI, Ollama, or custom)
- Setting model preferences
- For Ollama: selecting a local model (no API key needed)

**Supported Providers:**

| Provider | API Key | Notes |
|----------|---------|-------|
| Gemini | Required | Google's free tier available |
| OpenAI | Required | Pay-as-you-go |
| Ollama | Not needed | Run AI locally |
| Custom | Required | Use your own API endpoint |

## show

Show current configuration.

```bash
max config show
```

## set

Set configuration value.

```bash
max config set <KEY> <VALUE>
```

## grab

Configure download preferences.

```bash
max config grab
```

Interactive wizard to set:
- Default video/audio quality
- Auto-strip playlist info
- Embed metadata
- Default type (video/audio)
- Default download folder
- Queue system enabled/disabled

## reset

Reset configuration to defaults.

```bash
max config reset [--global | --local]
```

## validate

Validate current configuration.

```bash
max config validate
```

## export

Export configuration to file.

```bash
max config export <file.json>
```

## import

Import configuration from file.

```bash
max config import <file.json>
```
