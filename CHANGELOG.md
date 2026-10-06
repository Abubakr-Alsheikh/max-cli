# Changelog

## 1.0.0 (2026-10-04)

The first stable release. Max now has three ways in (commands, an AI agent and a dashboard) that share one description of every action, so they offer the same options and run the same code.

### New

- **AI agent.** `max "<request>"`, `max ai ask` and `max ai chat` plan the steps and run Max's own commands. The agent asks before it moves, overwrites or deletes files, stays inside the folders you work in, runs independent actions side by side, works through many files in one step and skips files that are done. `--dry-run` shows the plan.
- **Main AI and a fallback.** OpenAI, OpenRouter, Gemini or a local Ollama, each with its own key and model. Max switches to the fallback when the main one fails. `max config setup` and the Settings page pick them.
- **Dashboard.** A bare `max` opens it: Home, Download, Video, Audio, Images, PDF, Files, AI, Activity, Extras and Settings pages, `Ctrl+P` to find any action, a jobs window, history and undo. Home shows your week, your activity by type, recent runs and the actions you use most. Each page shows as a neon code in its own colour (`02 DOWNLOAD`); `max config setup-font` installs a Nerd Font and sets it in Windows Terminal, and the pages then show icons.
- **Several files at once.** Commands that work on one file also take several files, a folder or a pattern, with `--recursive` and `--redo`. Max skips files that already have a result and runs the rest side by side.
- **Background jobs.** `--queue` hands long jobs to a worker that keeps going after you close the terminal. `max queue start`, `status`, `cancel` and `retry` control it. The CLI, the dashboard and the worker share one queue.
- **Downloads.** A rebuilt `max grab` and Download page: previews, quality choices, playlists, a queue and `max grab pot-setup` for YouTube 403 errors.
- `max images convert` reads SVG (drawn by resvg, masks and filters included), AVIF, ICO, PSD and more, and writes AVIF, GIF, BMP, TIFF and ICO besides WebP, JPG and PNG. HEIC works with `pillow-heif` installed.
- `max --version`.
- A mistyped group (`max vidoe`) answers "Did you mean 'video'?" instead of going to the agent.

### Fixed

- Commands that report an error exit 1, so scripts can tell.
- FFmpeg downloads itself once, even when several jobs need it at the same time.
- Gemini 3 tool calls work (thought signatures).
- `max ai create` and `edit` use the image models you picked.
- A transparent image converted to JPG gets a white background, not a black one.
- A file name with brackets (`Song [Live].mp4`) is a file, not a pattern.
- Two files whose results would share a name no longer write one file at once.
- Backups made in the same second no longer replace each other.
- The activity log and the task queue keep every writer's changes when several processes write at once, and an unreadable file is never saved over.
- A worker that keeps crashing on one task stops retrying it.
- A plugin written like the README example no longer stops every command.

### Changed

- Python 3.9 to 3.12.
- The dashboard is part of the base install; the `tui` extra is empty.
- Settings that nothing read were removed; the Settings page and `max config validate` point out old ones in your settings file.

## 0.4.0

The release before the dashboard and the agent.
