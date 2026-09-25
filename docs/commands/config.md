# Config Commands

## setup

Interactive wizard to configure AI providers and models.

```bash
max config setup
```

The wizard walks you through:

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

Show which config files Max loads, and the AI models and endpoint it uses.

```bash
max config show
```

## save

Copy the `.env` file in the current folder to your global settings (`~/.max_config.env`). Max asks before it overwrites the global file.

```bash
max config save [--force]
```

**Options:**

- `--force`, `-f` - Overwrite the global config without asking

## grab

Configure download preferences.

```bash
max config grab
```

The wizard asks for:
- Default video/audio quality
- Auto-strip playlist info
- Embed metadata
- Default type (video/audio)
- Default download folder
- Queue system enabled/disabled

## reset

Delete your config files so Max falls back to its defaults. Max asks before it deletes each file.

```bash
max config reset [--global | --local]
```

**Options:**

- `--global` - Delete only the global config (`~/.max_config.env`)
- `--local` - Delete only the `.env` file in the current folder

With neither flag, Max offers to delete both.

## validate

Check your settings and list any value outside its allowed range.

```bash
max config validate
```

## export

Save your settings to a JSON file.

```bash
max config export [-o FILE] [--include-defaults] [--include-secrets]
```

**Options:**

- `-o` - Output file (default: `max-config.json`)
- `--include-defaults` - Include settings you never changed
- `--include-secrets` - Also write your `OPENAI_API_KEY`

The export leaves your API key out, so you can share the file. With `--include-secrets` it contains the key in plain text: keep that file private and never commit it.

## import

Load settings from a JSON file. Max asks before it overwrites an existing config file.

```bash
max config import FILE [--global | --local]
```

**Options:**

- `--global` / `--local` - Write to the global config or to `.env` in the current folder (default: `--global`)

## setup-ffmpeg

Download FFmpeg for your platform into `~/.max_cli/bin/` and check that it runs.

```bash
max config setup-ffmpeg [--force]
```

**Options:**

- `--force`, `-f` - Download FFmpeg again even if Max already has it

This command:
- Detects your OS and architecture
- Downloads the appropriate FFmpeg binary
- Validates the binary after download
- Stores it in `~/.max_cli/bin/` for automatic resolution
