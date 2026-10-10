# Changelog

## Unreleased

### New

- **The AI agent works on whole folders.** One request covers a folder and its subfolders, narrowed by name, size or age ("convert every m4a under Music to mp3"). You get one question with the file count, size and skipped files; big batches of long jobs go to the background queue; the dashboard shows one card per batch with its progress. A dry run lists the files it would run on.
- **The agent checks its work.** A missing or empty result counts as a failure and the agent says so.
- **The agent remembers.** Tell it a lasting fact or preference and later sessions start with it. `max ai memory` lists the notes, `--forget ID` deletes one and `--clear` deletes them all.
- The agent can check the queued jobs ("is my download done?") and undo Max's last file change.
- **The agent shows its plan.** Before multi-step work it lists the steps and waits: go ahead, stop, or say what to change. When a request is unclear it asks you one question with choices instead of guessing. On the dashboard both open a dialog.
- **The agent knows where you are.** Each request carries what the folder holds, the running jobs and Max's last action.
- **The agent sees the computer.** It reports free disk space, memory, CPU and battery, lists the programs using the most memory, opens a file, folder or link you ask to see (never programs), and asks the vision model about an image.
- **The agent can stop a program** you name, after asking; never the system's own.
- **Commands, if you allow them.** Turn on Settings > AI agent > Let the agent run commands and the agent can run a program with its arguments when no Max action fits, after showing you the command and getting your yes. Off by default.
- **A cheaper model for summaries** (`AI_FAST_MODEL`).
- `scripts/agent_eval.py` scores the agent's choices with your real model.
- **Stop the agent:** Ctrl+C once (or Stop on the AI page) ends the request after its current step; a second Ctrl+C quits.
- **Undo a whole request:** "undo what you just did" or `max ai undo` moves the files the last request made into Max's backups and reverses the changes it recorded.
- **Job notices:** the dashboard shows a notice when a queued job finishes or fails, and the agent hears about jobs that ended since your last request.
- **Notes on the dashboard:** the AI page's Notes button shows, adds and deletes what the agent remembers.
- **The agent picks the right one of similar actions.** Every action it can run has a guide: what it's for, which similar action to use instead, and the arguments that matter ("not for music track numbers: audio batch"), so "fix the numbering of my songs" sets the track numbers instead of renaming the files. After you say no to an action it doesn't ask about it again in the same request, and an answer in words counts as your instruction. A request may use up to 100,000 tokens.
- Long chats stay within the token limit: Max summarises the oldest turns. `ai chat` saves after every request, so Ctrl+C no longer loses the session.
- **Tags and folders for downloads.** `max grab download` and the Download page's new Tags card set the artist, album, genre and year written into the files. A playlist gives the album its name and numbers the tracks by their place in it (`3/43`); titles like `Artist - Song` give the artist. `--sort-into album` or `artist/album` saves into `Album/` or `Artist/Album/` folders. The Tags card shows for audio, and for video when you tick Tags.

### Changed

- The Download page has one **Whole playlist** box instead of "No playlist" and "Strip playlist". Off, a link to a video inside a playlist checks and downloads only that video; on, it lists the playlist's items to tick. The new Items box ticks the first N (`10`) or ranges (`5-20`, `1-3,7`), and a line counts the ticked items and their length.

### Fixed

- The agent's relative paths and patterns (`music/*.m4a`) now start in the agent's folder. They started in the folder Max was launched from, so a batch could find no files and the model retried call after call.
- The agent no longer runs an identical action twice in one request, and dry runs tell the model nothing ran on purpose.
- Downloaded MP3s no longer show track 63. ffmpeg put the link into the old ID3v1 tag, and some readers, Max's own among them (mutagen before 1.48), took its last character, `?`, for track 63. Max rewrites that tag after each download, and `max audio` ignores the false number in older files.
- The Browse window's **Max downloads** place opens the folder the Download page saves into, not the empty folder of the Save to setting. Folder pickers list the page's files too, dimmed, so a folder of songs no longer looks empty.

## 1.0.0 (2026-10-06)

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
