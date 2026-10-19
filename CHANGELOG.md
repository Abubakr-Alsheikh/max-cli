# Changelog

## 1.2.1 (2026-10-19)

FFmpeg installs again on every system, and the Windows installer no longer trips Windows Defender.

### Fixed

- **FFmpeg installs again on every system.** The Windows download link answered 404, the macOS source shut its download API, and the Linux one stopped answering. Max now installs FFmpeg with winget (Windows) or Homebrew (macOS) when you have them, else downloads it from the next source that works (gyan.dev, BtbN, johnvansickle.com, Martin Riedl), checks it against the SHA-256 its site publishes, and installs `ffprobe` too. When nothing works, it says which sources failed and how to install FFmpeg yourself, without a traceback.
- **Windows Defender blocked the Windows installer.** It downloaded uv's installer script and ran it straight away, a pattern Defender stops because malware uses it too. It now never runs a downloaded script: it gets uv with winget (Windows' own package manager), or from uv's official zip checked against its published SHA-256. It also turns on TLS 1.2 for older Windows, and has a copy on Max's website for networks that block `raw.githubusercontent.com`. The guides now lead with two winget commands, which need no script at all.

### Docs

- **[Is Max Safe?](https://Abubakr-Alsheikh.github.io/max-cli/safety/)**, a page on what Max installs and from where, and what to do when an antivirus stops `max.exe`, `ffmpeg.exe` or the installer.

## 1.2.0 (2026-10-13)

Compress to a size, cut the pauses out of recordings, transcripts and subtitles with Gemini, download only part of a video, and an easier install that tells you when to update.

### New

**Video, audio and downloads**

- **Compress to a size.** `max video compress clip.mp4 --size 25MB` works out the bitrate from the video's length and encodes in two passes, so the file lands just under the size, for mail and chat upload limits. `max images compress --size 2MB` and `max pdf compress --size 5MB` do the same for images and PDFs. The dashboard's forms and the AI agent take the size too ("make this video fit in 25 MB").
- **Cut the pauses.** `max video cut-silence lecture.mp4` removes the dead air from talks, lectures, podcasts and voice notes (jump cuts), keeping a little of each pause so words aren't clipped. `--threshold`, `--min-silence` and `--padding` tune it. It works on video and audio files, on folders and in the queue, and on the dashboard's Video page.
- **Transcripts and subtitles.** `max audio transcribe meeting.m4a` writes what was said, and `-f srt` writes subtitles for a video. Max sends only the sound to Google Gemini (it needs `GEMINI_API_KEY`) and deletes the upload afterwards. `--prompt` adds your own instructions: translate, summarise, name the speakers. It runs on folders and in the queue, on the dashboard's Audio page, and the AI agent can use it.
- **Download part of a video.** `max grab download URL --start 1:00 --end 5:00` fetches only that stretch, as video or MP3, without downloading the whole video. The file's name ends in the times (`Talk (1.00-5.00).mp4`), and `--exact-cuts` starts it on the second. The Download page has a **Part** card: pick Only part and type From and To (a link's `t=1m30s` fills From). It checks the times against the video's length as you type and shows the part's length and size. The AI agent can do it too ("download minutes 1 to 5 of this").

**Installing and updating**

- **One-line installers.** `install.ps1` (Windows) and `install.sh` (macOS, Linux) install uv when it's missing (uv brings its own Python), then Max, and check that it starts. The new [Start Here](https://Abubakr-Alsheikh.github.io/max-cli/start-here/) guide walks someone who has never used a terminal from opening one to a finished first job.
- **Update notices and `max update`.** Max tells you when a new version is out: one line after a command and a notice in the dashboard, checked at most once a day. `max update` installs it the way you installed Max (uv, pipx or pip), keeping extras. On Windows it updates from a small window that waits for Max to close, because updating a running Max broke the install. The dashboard's **Settings** > **Maintenance** shows the newest version and updates in one click. **Tell me when a new Max is out** (`UPDATE_CHECK`) turns the checks off.
- **`max doctor`** checks FFmpeg, the AI, transcripts, the YouTube fix, your folders, old settings and OCR, and gives the fix for each problem.
- `python -m max_cli` runs Max when the `max` command isn't on your PATH.

### Changed

- The Download page's **Options** card sits under **Output** on the right, so the page has no gap under Output.

### Fixed

- `max images compress` and `convert` on a folder no longer overwrite one image with another when two share a name (`cat.png` and `cat.jpg` both becoming `cat.jpg`). They come out as `cat_png.jpg` and `cat_jpg.jpg`.

## 1.1.0 (2026-10-10)

A smarter AI agent that works on whole folders, plans and checks its work, remembers what you tell it and can be stopped and undone; and downloads that come out tagged and sorted.

### New

**The AI agent**

- **Whole folders in one step.** One request covers a folder and its subfolders, narrowed by name, size or age ("convert every m4a under Music to mp3"). You get one question with the file count, the size and the files it skips as done; big batches of long jobs go to the background queue; the dashboard shows one card per batch with its progress. A dry run lists the files it would work on.
- **Plans and questions.** Before multi-step work it shows its plan and waits: go ahead, stop, or say what to change. When a request is unclear it asks one question with choices instead of guessing, and an answer in words counts as your instruction.
- **It picks the right action.** Every action it can run has a guide: what it's for, which similar action to use instead, and the settings that matter. "Fix the numbering of my songs" sets the track numbers instead of renaming the files.
- **It checks its work.** A result that is missing or empty counts as a failure, and it tells you.
- **It remembers.** Tell it a lasting fact or preference ("my music lives in D:/Music") and later sessions start with it. `max ai memory` lists, `--forget`s and `--clear`s the notes; the AI page's **Notes** button shows, adds and deletes them.
- **It knows where you are.** Each request carries what the folder holds, the jobs running and the jobs that finished since your last request, and Max's last action.
- **Stop and undo.** Press Ctrl+C once (or **Stop** on the AI page) to end a request after its current step. Say "undo what you just did" or run `max ai undo`: the files the last request made move to Max's backups and the moves, renames and deletes it recorded are reversed.
- **It sees the computer.** Free disk space, memory, CPU and battery; the programs using the most memory; it stops a program you name after asking (never the system's own); it opens a file, folder or link you ask to see (never programs); and it asks the vision model about an image.
- **Commands, if you allow them.** Turn on Settings > AI agent > Let the agent run commands, and it can run a program with its arguments when no Max action fits, after showing you the command and getting your yes. Off by default.
- **Long chats** stay within the token limit (Max summarises the oldest turns), a request may use up to 100,000 tokens, and `AI_FAST_MODEL` can name a cheaper model for those summaries. `ai chat` saves after every request.
- **Job notices.** The dashboard tells you when a queued job finishes or fails.

**Downloads**

- **Tags and folders.** `max grab download` and the Download page's Tags card set the artist, album, genre and year written into the files. A playlist gives the album its name and numbers the tracks by their place in it (`3/43`); titles like `Artist - Song` give the artist. `--sort-into album` or `artist/album` saves into `Album/` or `Artist/Album/` folders.

### Changed

- The Download page has one **Whole playlist** box instead of "No playlist" and "Strip playlist". Off, a link to a video inside a playlist downloads only that video; on, it lists the playlist's items to tick. The Items box ticks the first N (`10`) or ranges (`5-20`, `1-3,7`), and a line counts the ticked items and their length. The Tags card shows for audio, and for video when you tick Tags.

### Fixed

- Downloaded MP3s no longer show track 63. ffmpeg put the link into the old ID3v1 tag, and some readers took its last character, `?`, for the track number. Max rewrites that tag after each download, and `max audio` ignores the false number in older files.
- The Browse window's **Max downloads** place opens the folder the Download page saves into. Folder pickers list the page's files too, dimmed, so a folder of songs no longer looks empty.
- The agent's relative paths and patterns (`music/*.m4a`) start in its own folder, so a batch no longer finds nothing and retries; it no longer runs an identical action twice in one request, or asks again about an action you declined.
- Undo history keeps its order when two changes happen within one tick of the clock, and so does Activity > History.
- PyPI shows Max's license and supported Python versions.

### For contributors

- `python scripts/ci_local.py` checks only what changed (1-3 minutes); `--quick` and `--full` run everything. `scripts/agent_eval.py` scores the agent's choices with a real model, and `scripts/release_plan.py` suggests the next version.

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
