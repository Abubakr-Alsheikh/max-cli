# Config Commands

## setup

Pick the AI Max uses and a fallback, each with its own API key and model.

```bash
max config setup
```

The wizard asks for:

- **Main AI:** `openai` (or any URL that speaks OpenAI's API), `openrouter`, `gemini` or `ollama`, then that provider's API key and model. Press Enter at the key to keep the saved one. Before asking for the model, the wizard lists the models your key can use.
- **Fallback:** another provider, or `none`, with its key and model. When the main AI fails (no credit left, a rate limit, a wrong key, an unknown model, the service down), Max sends the same request to the fallback and stays on it for the rest of that run.
- **Image model** for `max ai create` and `edit`.

It changes only these settings; the rest of `~/.max_config.env` stays.

**Providers:**

| Provider | API key setting | Model setting | Notes |
|----------|-----------------|---------------|-------|
| OpenAI or a custom URL | `OPENAI_API_KEY` (+ `OPENAI_BASE_URL`) | `AI_MODEL` | Pay as you go; any OpenAI-compatible URL |
| OpenRouter | `OPENROUTER_API_KEY` | `OPENROUTER_MODEL` | `openrouter/free` picks a free model |
| Google Gemini | `GEMINI_API_KEY` | `GEMINI_MODEL` | Free key at aistudio.google.com/apikey; for example `gemini-2.5-flash` |
| Ollama | none | `OLLAMA_MODEL` | Runs on this computer (`OLLAMA_BASE_URL`) |

For example, free OpenRouter models first and Gemini when they run out:

```ini
AI_PROVIDER=openrouter
OPENROUTER_API_KEY=sk-or-...
AI_FALLBACK_PROVIDER=gemini
GEMINI_API_KEY=AIza...
```

Settings from before `AI_PROVIDER` keep working: without it, Max uses Ollama when `OLLAMA_ENABLED=true`, otherwise `OPENAI_API_KEY` with `OPENAI_BASE_URL` and `AI_MODEL`. `max config show` names the main AI and the fallback, and `max config validate` warns when one has no key.

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

Check your settings and list any value outside its allowed range. It also names settings your `~/.max_config.env` still sets that Max no longer has (`APP_NAME`, `BATCH_SIZE`, `GRAB_AUDIO_FORMAT`, `GRAB_QUEUE_ENABLED`, `PROGRESS_BAR`, `VERBOSE`). Max ignores them; delete those lines, or press **Remove them** on the dashboard's Settings page.

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
