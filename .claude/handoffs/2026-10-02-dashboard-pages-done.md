# Session Handoff: Every command group has its dashboard page

**Date:** 2026-10-02 **Project:** `D:\GitHub\Personal\max-cli` **Session:** continued from `2026-10-01-tool-pages.md`

**Goal (maintainer's words):** "handover", after merging #45.

## Current State

- **Task:** the dashboard rework in `PLANS/active/dashboard-tool-pages.md`: one page per command group, built on a shared layout. The maintainer runs `max`, tries a page, then asks for changes by description or screenshot.
- **Phase:** between pieces. Every catalog group has a page now. The Tools page, Queue page and History page are gone (folded into group pages and the Activity page).

## Repository State

- **Branch:** `main` at `657439e` (Merge PR #45). Working tree clean. No open PRs except this handoff's.
- **Merged since the last handoff:**
  - #41 Images page; Settings moved to `,`; sidebar arrow keys as priority bindings; `Select.BLANK` crash fix.
  - #42 Browse window (`widgets/path_picker.py`): places, pins, recent folders, Back/Up, filter, file/folder/save modes.
  - #43 Files page on the shared layout; "Open on the PDF page" link on every page; chip grids drop columns to fit names; prefs save retries on a Windows file lock.
  - #44 `audio` group in the catalog plus the Audio page; Tools page removed; `max audio` fixes (MP3 comment, M4A composer, M4A tag names, `batch --track`); Windows redirected-output crash fix in `main()`.
  - #45 Activity page (Queue, History, Undo tabs); undo steps back one change at a time and removes folders it created; `command_registry.py` and `command_executor.py` deleted.
- **Stash:** `stash@{0}: WIP on main: 5378faa` belongs to the maintainer. Leave it alone; never use `git stash`.
- **The maintainer's real `~/.max_cli`:** never touch it. Manual tests run against a throwaway home (see Pitfalls).

## Plan Status

- **`PLANS/active/dashboard-tool-pages.md`:** Settings, shared layout, Video, PDF, Images, Files, Audio and Activity are done. Open steps:
  - `Ctrl+P` finds every action and opens it on its page.
  - Extras page after the `tools` group (share, qr, paste, copy) joins the catalog; key `0` is free for it.
  - AI page replacing Chat, with the agent (roadmap step 4).
  - Results: a short list of finished runs on each page, with Open.
- **Sidebar today:** 1 Home, 2 Download, 3 Video, 4 Audio, 5 Images, 6 PDF, 7 Files, 8 Chat, 9 Activity, `,` Settings. Key `0` unused.
- **`PLANS/active/command-catalog.md`:** groups ported: video, grab (download), images, pdf, files, audio. Step 6 cleanup done. Still to port: `ai`, `tools`. Step 5 (agent tool views) is open.
- **Open decision (ask the maintainer):** nine settings no code reads (`APP_NAME`, `BATCH_SIZE`, `CONFIRM_DESTRUCTIVE`, `DOWNLOAD_TIMEOUT`, `GRAB_AUDIO_FORMAT`, `GRAB_QUEUE_ENABLED`, `MAX_RETRIES`, `PROGRESS_BAR`, `VERBOSE`). Recommendation given: wire `DOWNLOAD_TIMEOUT`, `MAX_RETRIES` and `CONFIRM_DESTRUCTIVE`, delete the other six, and warn at startup when a `.env` still sets a removed one. Not decided yet; deleting a field can break a `.env` that sets it.

## Quality Gates (main, 2026-10-02)

- `python scripts/ci_local.py --full`: passed in 693 s on #45's head. GitHub: 14/14 on every merged PR.
- pytest: 1361 passed, 1 skipped, 3 xfailed (full suite, Python 3.11).
- mypy: 32 errors, matching `mypy-baseline.txt` (34 at the start of #45, 36 a session earlier).
- ruff clean.

## What We Did

- **Pages:** Images, Files, Audio and Activity on the shared `ToolPage`/spec design, plus the Browse window used by every Browse button.
- **Shared layout grew:** `ToolPageSpec.file_title`, `kinds` (which page a file kind belongs to; other pages offer "Open on the X page"), `no_fill`, `action_defaults` (dashboard-only defaults, e.g. audio organize = artist-album), `prefill` (fill a form from the picked file in a thread, e.g. audio `set` gets the current tags). `file_param` fills FILE params, else input FOLDER params, never `output`/`output_dir`; a folder param gets a picked file's folder.
- **Core additions:** `images.describe`, `files.describe`, `audio.describe`, `core/operations/audio.py`, `common/file_kinds.py`, `TransactionLog.make_dirs`/`OP_MKDIR`/`next_to_undo`.
- **Fixes found by testing for real:** see the merged PR list. The audio set of fixes came from running every `max audio` command on generated MP3/M4A/FLAC/OGG/WAV/Opus files.

## Decisions Made

- **Tools page removed** once every catalog action had its group's page (the plan's rule); 12 pages didn't fit the keys.
- **Queue and History became Activity tabs** (plan decision), plus an Undo tab; key 0 freed for Extras.
- **Settings on `,`** when pages outgrew 1-9 and 0. Bindings use `SETTINGS_KEY_NAME = "comma"` because Textual splits binding keys on commas.
- **Audio organize defaults to artist-album on the dashboard** (the maintainer's earlier choice), artist on the CLI. Lives in `tool_pages.AUDIO.action_defaults`, tested in `tests/test_presets.py`.
- **Hidden CLI options are compatibility no-ops** (`audio clear --keep-duration`); the catalog drift test skips hidden options.
- **Undo is a stack:** each `max files undo` reverses the newest group not undone yet.

## Pitfalls (hit this session)

- **Test against a throwaway home, never `~/.max_cli`.** For the CLI: a script that sets `HOME` and `USERPROFILE` to a temp folder (`$CLAUDE_JOB_DIR/tmp/audiotest/run.sh` was the pattern). For the dashboard: `scripts/tui_screenshot.py`'s `_use_throwaway_home()`. FFmpeg is at `C:\ffmpeg\bin` for generating sample media.
- **Textual 8:**
  - `Select.BLANK` is `False`; `Select.NULL` marks empty. Leave `value` out, use `is_blank()`/`clear()`.
  - A `str` DataTable cell is parsed as markup; a `Content` cell measured 2 columns wide. Use Rich `Text` for file names.
  - `Button.name` has no setter.
  - Priority bindings on the sidebar: an overflowing scroll area otherwise eats up/down.
  - The app CSS `DataTable { height: 1fr; min-height: 8 }` beats widget CSS; paged tables need an exception in the app CSS (`#download-history-table, #history-table, #undo-table`).
- **mutagen:** easy ID3 has no "comment" and easy MP4 no "composer"; `audio_metadata_engine._register_easy_keys` adds them. An easy getter must raise `KeyError` for a missing tag. MP3/WAV are read from raw ID3 frames so custom `TXXX` tags show.
- **Windows output:** redirected stdout uses the code page (cp1256 here); `main.tolerate_unencodable_output()` replaces what it can't encode.
- **Click expands `*.mp3` only for the CLI on Windows** (`windows_expand_args`); operations expand patterns and folders themselves (`audio.resolve_audio_files`).
- **Tests and timing:**
  - Wait for the real end state with `wait_until`, not a first condition that an earlier state also meets (two races this session: the Browse path box, the History search).
  - macOS CI caught a layout read one pass too early (chip width).
  - Windows CI caught a prefs file lock (`ui_prefs.save_pref` retries 3 times, then skips).
- **CI on this machine:**
  - Run `--full` through the Monitor tool (`python scripts/ci_local.py --full | tee log | grep --line-buffered -E "^(PASS|FAIL)|All checks"`).
  - The startup-time test (0.2 s target) fails now and then under load (0.203 s); rerun. Never fake the `ci-local.json` stamp.
  - The stop hook's pytest times out at 300 s when it overlaps `--full`.
- **Shell:** heredocs with nested quotes broke twice; write edit scripts with the Write tool, then run them.
- **The maintainer's own `max` may be running** (it showed in the process list); don't kill Python processes blindly.

## Context to Remember

- Platform: Windows 11, Python 3.11 (`python`), Git Bash, uv, code page cp1256.
- Maintainer preferences:
  - Terse replies (caveman style); commits, PRs, docs and plans in plain English (stop-slop).
  - One branch and PR per piece; merge only when they say "merge".
  - Honest recommendations, not agreement ("don't take up my opinion").
  - They care about looks, smoothness and usefulness. Check screenshots at 140x44, 120x40 and 90x30, and offer improvements found while testing.
  - "Make sure it's all working": run the real commands on real files, not only the unit tests.
- Don't touch the stash, `~/.max_cli`, or `pyproject.toml` dependencies without asking.

## Next Steps

1. [ ] `git checkout main && git pull`; confirm `657439e` or later and that this handoff is merged.
2. [ ] Ask the maintainer about the nine unused settings (recommendation above).
3. [ ] `Ctrl+P` action search: a Textual command palette provider over `catalog.actions_for(group, Surface.DASHBOARD)`; picking one navigates to its page (`TOOL_PAGES` spec, or Download for `grab`) and calls `show_action`. Tests, docs, plan step.
4. [ ] Port the `tools` group to the catalog (`core/operations/tools.py`, `core/catalog/groups/tools.py`, drift test), then an Extras page on key `0`.
5. [ ] AI page replacing Chat, with the agent: needs the catalog's agent tool views (command-catalog plan step 5) first.

## Files to Review on Resume

- `PLANS/active/dashboard-tool-pages.md`: the plan and its open steps.
- `src/max_cli/interface/tui/widgets/tool_page.py` and `interface/tui/tool_pages.py`: the shared layout and every page spec.
- `src/max_cli/interface/tui/widgets/activity_panel.py`, `history_panel.py`, `undo_panel.py`: the newest page.
- `.claude/skills/max-tui-design/SKILL.md`: design rules and the pitfalls list (several added this session).
- `src/max_cli/core/catalog/`: groups, runner and the drift test (`tests/test_catalog_drift.py`).
