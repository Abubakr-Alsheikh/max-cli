# Config Commands

## setup

Pick the AI Max uses and a fallback, each with its own API key and model.

```bash
max config setup
```

The wizard asks for:

- **Main AI:** `openai` (or any URL that speaks OpenAI's API), `openrouter`, `gemini` or `ollama`, then that provider's API key and model. Press Enter at the key to keep the saved one. For `openai` the wizard also asks for a custom URL (empty for OpenAI itself). Ollama needs no key, so the wizard asks where it runs instead. Before it asks for the model, the wizard lists up to 15 models your key can use.
- **Fallback:** another provider, or `none`, with its key and model. When the main AI fails (no credit left, a rate limit, a wrong key, an unknown model, the service down), Max sends the same request to the fallback and stays on it for the rest of that run.
- **Image model** of the main AI and of the fallback, for `max ai create` and `edit` (empty: that provider makes no images). The wizard names a few image models to pick from. Ollama has no image model. Images follow the main AI and its fallback like text does.

It changes only these settings; the rest of `~/.max_config.env` stays.

**Providers:**

| Provider | API key setting | Model setting | Notes |
|----------|-----------------|---------------|-------|
| OpenAI or a custom URL | `OPENAI_API_KEY` (+ `OPENAI_BASE_URL`) | `AI_MODEL` | Pay as you go; any OpenAI-compatible URL |
| OpenRouter | `OPENROUTER_API_KEY` | `OPENROUTER_MODEL` | `openrouter/free` picks a free model |
| Google Gemini | `GEMINI_API_KEY` | `GEMINI_MODEL` | Free key at aistudio.google.com/apikey; `gemini-flash-latest` follows Google's newest Flash |
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

Show which config files Max loads: `~/.max_config.env`, and a `.env` in the current folder, whose settings win. Below that it names the main AI and the fallback with their models (and `(no API key)` when one has none), the image model (`AI_IMAGE_MODEL`) and the custom URL when you set one.

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
- Default video/audio quality (`s`, `m`, `h` or `x`)
- Auto-strip playlist info
- Embed metadata
- Default type (video/audio)
- Default download folder

It saves these to `~/.max_config.env`.

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

Check your settings and list any value outside its allowed range, and a main AI or fallback with no API key. It also names settings your `~/.max_config.env` still sets that Max no longer has (`APP_NAME`, `BATCH_SIZE`, `GRAB_AUDIO_FORMAT`, `GRAB_QUEUE_ENABLED`, `PROGRESS_BAR`, `VERBOSE`). Max ignores them; delete those lines, or press **Remove them** on the dashboard's Settings page.

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
- `--include-defaults` - Write every setting, not only the AI and download ones
- `--include-secrets` - Also write your API keys (`OPENAI_API_KEY`, `OPENROUTER_API_KEY`, `GEMINI_API_KEY`)

Without `--include-defaults`, the file holds `AI_PROVIDER`, `AI_FALLBACK_PROVIDER`, `OPENAI_BASE_URL`, `AI_MODEL`, `OPENROUTER_MODEL`, `GEMINI_MODEL`, `AI_IMAGE_MODEL` and the `GRAB_*` download settings, each one only when it has a value. The export leaves your API keys out, so you can share the file. With `--include-secrets` it contains the keys in plain text: keep that file private and never commit it.

## import

Load settings from a JSON file. The settings in the file replace the whole config file, so Max asks before it overwrites one that exists.

```bash
max config import INPUT [--global | --local]
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
- Stores it in `~/.max_cli/bin/`, where Max looks for FFmpeg when it isn't on your `PATH`
