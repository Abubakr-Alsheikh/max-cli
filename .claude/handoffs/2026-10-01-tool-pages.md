# Session Handoff: Dashboard pages per command group (Settings, Video, PDF)

**Date:** 2026-10-01 **Project:** `D:\GitHub\Personal\max-cli` **Session:** continued from `2026-09-30-dashboard-redesign.md`

**Goal (maintainer's words):** "merge and make a handover", after the PDF page.

## Current State

- **Task:** turn the dashboard into one page per command group (`PLANS/active/dashboard-tool-pages.md`). The maintainer tests each page by running `max` and asks for changes by description or screenshot.
- **Phase:** between pages. Video and PDF are done; Images is next.

## Repository State

- **Branch:** `main` at `007b7e6` (Merge PR #39). Working tree clean. No open PRs.
- **Merged this session:**
  - #35 Download page, second round: compact options, paged history, richer preview, TOOLS card, YouTube fix button, Check spinner; Simple/Advanced switch removed.
  - #36 Queue page in the command-center style.
  - #37 Settings page (replaced Config, System and Analytics).
  - #38 Video page and the shared `ToolPage` layout.
  - #39 PDF page.
- **Stash:** `stash@{0}: WIP on main: 5378faa` belongs to the maintainer. Leave it alone; never use `git stash`.
- **The maintainer's real `~/.max_cli`:** don't touch it. One test task leaked into it this session and was removed by id (see Pitfalls).

## Plan Status

- **`PLANS/active/dashboard-tool-pages.md`** (decided 2026-09-30):
  - Done: Settings, shared layout, Video, PDF.
  - Next, in order: Images, Files on the same layout (a folder instead of a file), Audio (port the `audio` group to the catalog first, then a page with a tag table), `Ctrl+P` finds every action, Activity (Queue and History as two tabs), AI page with the agent, Extras after the `tools` port. Tools goes when every group has a page.
  - Target sidebar: 1 Home, 2 Download, 3 Video, 4 Audio, 5 Images, 6 PDF, 7 Files, 8 AI, 9 Extras, 0 Activity, Settings on `,`. Today it is Home, Download, Video, PDF, Tools, Files, Chat, Queue, History, Settings (keys 1-9, 0).
  - Open decision: nine settings nothing reads (`APP_NAME`, `BATCH_SIZE`, `CONFIRM_DESTRUCTIVE`, `DOWNLOAD_TIMEOUT`, `GRAB_AUDIO_FORMAT`, `GRAB_QUEUE_ENABLED`, `MAX_RETRIES`, `PROGRESS_BAR`, `VERBOSE`): delete them from `config.py` or make them work. Ask the maintainer.
- **`PLANS/active/dashboard-design-system.md`:** R0-R3 done; R4 now runs through the tool-pages plan.
- **`PLANS/active/command-catalog.md`:** `audio`, `ai` and `tools` are still not in the catalog.

## Quality Gates (main, 2026-10-01)

- `python scripts/ci_local.py --full`: passed in 651 s on the last PR (#39). Every PR this session passed GitHub's 14 checks before merging.
- pytest: about 1190 tests per Python; dashboard suite 197 passed, 1 skipped.
- mypy: 36 errors, matching `mypy-baseline.txt` (dropped from 37 when the old panels went).
- ruff clean.

## What We Did

- **Pages:** Download round two, Queue, Settings, Video, PDF (PR list above). Analytics deleted; Config and System merged into Settings.
- **Shared layout:** `widgets/tool_page.py` plus a `ToolPageSpec` per page in `interface/tui/tool_pages.py`. A page is a spec (group, header, action sections) and a `describe(path) -> Content` run in a thread. A test fails when a dashboard action of the group sits in no section.
- **Core `describe` operations:** `video.describe` (ffprobe via `FFmpegEngine.probe_media`, never downloads FFmpeg) and `pdf.describe` (`PDFEngine.inspect_pdf`: pages, paper size, form fields, locked, scanned).
- **Settings:** shows only settings code reads (a test enforces it), saves only changed keys through `common/settings_file.py`, warns when a local `.env` overrides them, and does upkeep (FFmpeg status, data size, cache and 30-day undo cleanup, reset).
- **Fixes found on the way:**
  - Pages start hidden (`#content > * { display: none }`); the Download page used to grab focus on the first frame and swallow number keys.
  - `workers.show_from_worker` hands thread-worker results to a page and skips them when the page is closing. Late results raised NoMatches and failed CI runs.
  - `ToolPage` and `ToolsPanel` keep a reference to their current form and fill it after awaiting the mount.
  - `scripts/ci_local.py` runs the `pytest` script like GitHub, not `python -m pytest`, which hid a broken `tests.` import.
  - `tests/interface/tui/waiting.wait_until` replaces fixed pause counts.
  - A blocking `started.wait(5)` in a Pilot test froze the event loop; it was the old "3.9 hang".

## Decisions Made

- **A page per command group** (maintainer, 2026-09-30), built from specs, not new classes.
- **Settings shows only settings that do something.** Unused ones stay in `config.py` until the maintainer decides.
- **Page numbers in text come from `SECTION_KEYS`.** Adding a page moves the keys; literals went stale twice.
- **Files page buttons open the group's page** when it has one (`FilesPanel.OpenAction` routing in `app.py`), else Tools.

## Pitfalls (hit this session)

- **Never run ad-hoc code against the real `~/.max_cli`.** A debug script added a task to the maintainer's real queue; their open dashboard ran it. Debug inside pytest or with the throwaway home from `scripts/tui_screenshot.py`. A memory note records this (`isolate-debug-scripts`).
- **Textual:**
  - Don't name a widget attribute `_task`, `_parent`, `_id`, `_classes` or `_nodes`; Textual uses them (`_task` crashed a row on mount).
  - `remove_children()` finishes later; a query right after can return the old widget.
  - `Input.action_submit` is a coroutine; in tests press Enter instead.
  - App CSS beats widget CSS: the app's `DataTable` rule made the Download history 35 rows tall.
- **CI on this machine:**
  - `--full` takes 600-750 s and was twice stopped for low memory as a background job. Run it through the Monitor tool (`python scripts/ci_local.py --full | grep --line-buffered -E "PASS|FAIL|..."`); it ran clean that way.
  - The stop hook's own pytest times out (300 s) when it runs during `--full`. That's load, not a failure.
  - The pre-push hook runs the quick CI (about 5 minutes); a `git push` can look stuck.
- **`ruff format src tests` reformats files nobody touched** (about 13 are unformatted at HEAD). Format only the files you changed.
- **Shell:** write edit scripts with the Write tool; heredocs mangle backslashes and quotes.

## Context to Remember

- Platform: Windows 11, Python 3.11 (`python`), Git Bash, uv. FFmpeg is installed at `C:\ffmpeg\bin`.
- Maintainer preferences:
  - Terse replies (caveman style); commits, PRs, docs and plans in plain English (stop-slop).
  - One branch and PR per piece. Merge only when they say "merge".
  - They ask for honest recommendations, not agreement ("don't take up my opinion").
  - They care about looks and smoothness; show screenshots (`scripts/tui_screenshot.py`, or a small script that picks a file, like the ones used for Video and PDF).
- Don't touch the stash, `~/.max_cli`, or `pyproject.toml` dependencies without asking.

## Next Steps

1. [ ] `git checkout main && git pull`; confirm `007b7e6` or later.
2. [ ] Images page: `images.describe` (dimensions, format, colour mode, size; for a folder, how many images and their total size) in `core/operations/images.py` through `ImageEngine`, a spec with the 4 actions, sidebar entry, tests, docs. Copy the PDF page's PR (#39) for the shape.
3. [ ] Files page on the shared layout: a folder picker, facts by file type, the 10 `files` actions.
4. [ ] Ask the maintainer about the nine unused settings.
5. [ ] Later: Audio catalog port, `Ctrl+P` actions, Activity tabs, AI page with the agent.

## Files to Review on Resume

- `PLANS/active/dashboard-tool-pages.md`: the plan and its steps.
- `src/max_cli/interface/tui/widgets/tool_page.py` and `interface/tui/tool_pages.py`: the layout and the Video and PDF specs.
- `.claude/skills/max-tui-design/SKILL.md`: design rules and pitfalls; read before any page work.
- `src/max_cli/interface/tui/workers.py`: how thread results reach a page.
