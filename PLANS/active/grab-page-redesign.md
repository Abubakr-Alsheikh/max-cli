# Plan: Grab (Download) Page Redesign

**Status:** In Progress
**Priority:** P0 (maintainer's top feature)
**Updated:** 2026-09-26
**Related:** `command-catalog.md` (build step 4), `dashboard-ui-redesign.md`, `paths-from-anywhere.md`

## Goal

Downloading from YouTube is the feature people use most. The Download page should make it easy for a beginner and flexible for someone who wants control.

## What the maintainer asked for (2026-09-26)

"We will focus more then in the grab page to let it be more useful and flexible to work with and easier, because it's now the most important feature because it download from youtube, so I want to let the UI and UX be so good."

Chosen for the first round:
1. **Preview before download.** Paste a link and see what it is before you download it.
2. **Playlist picker.** Choose which playlist items to download.
3. **Several downloads at once**, each with its own progress.
4. **Simple or advanced form, your choice:** "let them choose the form, if it's simple or advance, so what fit for both of them".

## What the page does today

- **Form:** URL box, Video or Audio, quality (360p to 4K), a separate "Res" box, an audio bitrate list, subtitles, metadata, "No Playlist", an output folder, and "Download Now" and "Queue" buttons. It warns when a URL was downloaded before.
- **Gaps:**
  - You learn nothing about the link (title, length, sizes, playlist items) until the download ends.
  - Playlists are all or nothing.
  - Only one download runs at a time.
  - "Cancel" sets a flag that yt-dlp never reads, so the download keeps going.
  - "Browse" only shows a hint.
  - "Clear History" deletes without asking.
  - The quality list and the "Res" box overlap.

## Design

### Core (`core/operations/grab.py`, no UI)

- **`probe(url) -> MediaInfo`**
  - For a single video: title, channel, duration, upload date, and the available heights with estimated sizes.
  - For a playlist: title, item count, and each item's index, title, duration and URL.
  - One yt-dlp `extract_info(download=False)` call. Results stay cached for the session, so the preview and the download don't fetch twice.
- **`download(url, ..., should_cancel=None, on_progress=None) -> ActionResult`**
  - Wraps `NetworkEngine.download_media`.
  - Returns the files it wrote.
  - `should_cancel` is checked in yt-dlp's progress hook, which raises to stop the download. Cancel then really cancels, and the partial files are removed.
- **Catalog entry `grab.download`**, so the Tools page and the agent get it too. The CLI `max grab download` keeps its interactive prompt and calls the same operation. The rest of the `grab` group (queue, status, history, pot-setup) gets catalog entries when the CLI side is ported.

### Download page layout

```
+--------------------------------------------------------------+
| Download                              ( Simple | Advanced )  |
| [ paste one or more links ................. ] [Paste] [Check]|
+--------------------------------------------------------------+
| PREVIEW                                                      |
|  How to Train Your Dragon - Trailer      Universal - 2:31    |
|  Quality: (Best) (1080p ~84 MB) (720p ~41 MB) (Audio MP3)    |
|  -- or, for a playlist --                                    |
|  My Mix - 24 videos     [Select all] [None] [Range 3-10]     |
|  [x] 1  Song one            3:12                             |
|  [ ] 2  Song two            4:05   ...                       |
+--------------------------------------------------------------+
| Save to: ~/Max Downloads                       [Browse]      |
| Advanced only: subtitles, metadata, exact height, player,    |
|                audio format and bitrate, file name pattern   |
|                        [Download] [Add to queue]             |
+--------------------------------------------------------------+
| DOWNLOADS                                                    |
|  Song one       ########----  64%  2.1 MB/s  0:12   [Cancel] |
|  Trailer        done  84 MB                 [Open folder]    |
|  Broken link    failed: HTTP 403            [Retry]          |
+--------------------------------------------------------------+
| HISTORY (search, re-download, clear with confirmation)       |
+--------------------------------------------------------------+
```

- **Simple mode:**
  - Paste a link and get the preview.
  - Pick one quality chip: Best, 1080p, 720p, 480p or Audio (MP3).
  - Download.

  Chips show only the qualities the video offers, with sizes.
- **Advanced mode** adds every other `grab download` option, with the same defaults as the CLI.
- The page remembers your choice of mode and your last settings.
- **Several links:** paste several (one per line). Each becomes a row in Downloads. Up to `GRAB_MAX_CONCURRENT` (new setting, default 3) run at once, and the rest wait.
- **Each row:** progress, speed and time left, plus **Cancel**, **Retry** and **Open folder**.
- **History:** Clear asks first. A row can be downloaded again with one click.

## Phases (one PR each, tests first)

1. [x] **G1: core.** Done 2026-09-26, branch `feat/grab-core`.
   - `probe`, cancellable `download`, the `grab.download` catalog entry, and the `GRAB_MAX_CONCURRENT` setting.
   - Tests with a mocked yt-dlp.
2. [x] **G2: page skeleton.** Done 2026-09-26, branch `feat/grab-page`.
   - The mode switch.
   - Link box with Paste and Check, and the preview card for a single video with quality chips.
   - Browse opens `PathPicker`.
   - A Downloads list with real Cancel.
3. [x] **G3: playlists.** Done 2026-09-26 in the page redesign (PR #21). The item picker (all, none, a range, single items), passed through as `playlist_items`.
4. [x] **G4: several at once.** Done 2026-09-26 (PR #21): paste several links and each becomes a download. The concurrency limit, Retry, Open folder and history clear with confirmation shipped with G2.
5. [x] **G5: CLI.** Done 2026-09-26. `max grab download` calls the same operation; the CLI's interactive prompt stays.

## Decisions

- 2026-09-26: Concurrent downloads run in dashboard thread workers, not in `TaskManager`, which runs one task at a time. "Add to queue" still uses the task queue.
- 2026-09-26, G1:
  - `NetworkEngine.download_media` now returns `files`, the final paths after merging or audio extraction. It reads them from yt-dlp's post-processor hook, with the progress hook as a fallback.
  - It also accepts `should_cancel`. A cancel raises `OperationCancelled` and removes only `.part` and `.ytdl` leftovers. A test caught the hook checking the cancel before it recorded the partial file, which would have left the file behind.
  - `grab.download` in the catalog reads `Setting(...)` defaults (quality, folder, type, metadata, playlist stripping) from the user's config when it runs.
  - The drift test checks `grab`'s operation now and its CLI after G5.
- 2026-09-26, G2:
  - The Download page was rewritten around `core/operations/grab.py`.
  - Advanced mode embeds `ActionForm(grab.download, include=..., embedded=True)`, so its options come from the catalog.
  - The Simple or Advanced choice and the last folder are saved in `~/.max_cli/dashboard_prefs.json` (`interface/tui/ui_prefs.py`).
  - Each download is a `DownloadRow`, run by a thread worker that waits for one of `GRAB_MAX_CONCURRENT` slots.
  - The old `grab` entries left `command_registry.py` and `command_executor.py`.
  - The page has no Paste button. Ctrl+V pastes into the link box, and reading the system clipboard would need a new dependency.
- 2026-09-26, maintainer feedback on G2: pressing Check crashed with a `MarkupError`, and the page was "not good in using it or looking at it".
  - **The crash.** The YouTube token helper (bgutil) timed out, and its error quoted a command line full of `[`. Neither Rich's nor Textual's `escape()` makes such text safe, so the dashboard now inserts untrusted text through `interface/tui/text.py:markup()`, using `$variables`, or as plain `Content`. The Download page, forms and chat all use it.
  - **The timeout.** `probe_info` retries once on the helper's `TimeoutExpired`, then gives a readable message. Downloads give the same message.
  - **The redesign.** The layout was checked with rendered screenshots (Textual SVG export to headless Chrome):
    - Cards: Link, "What you'll get" and Advanced options.
    - A Simple | Advanced toggle, and Video | Audio (MP3) buttons.
    - Quality chips with rounded sizes, three per row, keeping your usual pick.
    - A download button that says what it will do ("Download 1080p · 78 MB", "3 of 12 items").
    - Tabs for Downloads, with a count of those running, and History, with Download again, Open folder and Clear.
  - **Flow.** The link is checked on its own 0.6 s after a paste, and Enter downloads once it's checked.
  - The sidebar is wider, so every label fits.
- 2026-09-26, G5:
  - `max grab download` now downloads through `core/operations/grab.download`. Terminal downloads now appear in the dashboard's History, which they didn't before, and the CLI lists the saved files.
  - `--no-process` now does what its help says: it queues without starting the queue.
  - The CLI's flags stay as they are (`--video`/`--audio`, `--no-meta`, `--index`), because renaming them would break scripts. The catalog drift test therefore checks `grab`'s operation but not its CLI flags; see `CLI_CHECKED_GROUPS` in `tests/test_catalog_drift.py`.
