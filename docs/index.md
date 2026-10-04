# Max CLI

Max is a terminal assistant that turns jobs like compressing a video, merging PDFs or downloading from YouTube into short commands. You can type the commands, ask the AI agent in plain words, or work in the dashboard.

```bash
max video compress ~/Videos --recursive      # every video in a folder tree
max pdf ocr scans/ --queue                   # OCR in the background
max "sort my Music folder by artist"          # the AI agent plans and runs it
max                                           # the dashboard
```

## Features

- **Video and audio:** compress, cut, convert, GIFs, volume, noise, color, music tags, sorting songs into folders. Max downloads FFmpeg when you first need it.
- **PDF:** merge, split, compress, OCR, watermark, lock, forms, compare.
- **Images:** compress, resize, convert (SVG, AVIF, ICO and more), strip GPS and camera data.
- **Downloads:** video or audio from YouTube and most other sites, with quality presets.
- **Files:** AI sorting, numbering, duplicates, backups, secure delete and undo.
- **AI:** an agent that runs Max's commands for you, plus image analysis and generation, search by meaning and data extraction. It works with OpenAI, OpenRouter, Gemini or a local Ollama, with a fallback provider.
- **Batches:** commands that work on one file also take several files, a folder or a pattern, and skip files that are done.
- **Background queue:** `--queue` hands a long job to a worker that keeps going after you close the terminal.
- **Dashboard:** a page per command group, live progress, history, undo and settings.

## Where to start

- [Installation](installation.md): install Max, FFmpeg, OCR and an AI provider.
- [Usage](usage.md): the three ways to use Max, batches, the queue and the agent.
- [Commands](commands/index.md): every command group and option.
- [Dashboard](commands/dashboard.md): pages and keys.
- [Config settings](api/config.md): every setting and its default.
