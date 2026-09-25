# Plan: Codebase Hardening

**Status:** In Progress (Phases 0-3 done, startup target open)
**Priority:** P0
**Updated:** 2026-09-25

## Goal

Fix the correctness and security bugs found in the September 2026 review. Then remove the structural duplication that keeps producing them (three history stores, TUI presets copied from the CLI), and close the test and doc gaps, so new features land on a stable base. No new user-facing features ship until Phase 1 is done.

Baseline on 2026-09-24:
- pytest: 209 pass, 1 skipped.
- ruff: clean.
- mypy: 58 errors in 21 files.
- `import max_cli.main`: about 570 ms, against the 200 ms target.
- `python .claude/hooks/check_rules.py --audit src/max_cli`: 84 violations.

## How to work this plan

- **One branch and one PR per phase:** `fix/hardening-p1-bugs`, `refactor/hardening-p3-stores`, and so on. Phases 1 and 2 can overlap. Phase 3 depends on the decisions below.
- **Bugs first:** every bug task starts with a failing regression test (skills `test-driven-development` and `max-testing`), then the fix.
- **Before each PR:** run the `max-review` skill. Tick boxes only when the code, tests and docs all exist (`max-plans`).
- **Sizes:** S is under 1 hour, M is half a day, L is a day or more.

## Decisions needed before Phase 3

- [x] **D1. One queue and history store.** Decided 2026-09-25: yes to both, including the WIP `download_history.py` (done in Phase 3).
  - Merge the `max grab` queue (`QueueManager`, `~/.max_cli/grab_history.json`) into `DaemonManager` + `task_queue` (`~/.max_cli/queue/history.json`)?
  - Fold the uncommitted `common/download_history.py` into that store instead of adding a third file?
  - Recommendation: yes to both. Put one persistence helper under `DaemonManager`, and migrate the old files on first load.
- [x] **D2. Plugin loading from `./plugins`.** Decided 2026-09-24: home directory only. Extra folders come from `"plugin_dirs"` in `~/.max_cli/plugins.json` (implemented in 1.7).
- [x] **D3. The "daemon".** Decided 2026-09-25: option A (done in Phase 3).
  - It's a `daemon=True` thread that dies when the CLI exits.
  - Option A: rename it to an in-process worker and remove the unused PID and log files.
  - Option B: build a real detached background process.
  - Recommendation: A now, and B as its own plan if it's ever needed.
- [x] **D4. Startup target.** Decided 2026-09-25: keep 200 ms and switch the event models to dataclasses (done). The target is still missed; see Phase 3 results.
  - Is 200 ms still the goal? The biggest single cost is pydantic models in `common/events.py` (about 150 ms).
  - Recommendation: keep the target, and switch the event models to `dataclasses` (Phase 3).

---

## Phase 0: Safety net (Completed 2026-09-24, branch `chore/hardening-p0`)

- [x] Add `mypy>=1.18`, `types-requests`, `types-pyperclip` and `types-psutil` to the `dev` extra in `pyproject.toml` (approved).
- [x] `scripts/mypy_baseline.py` plus a new `typecheck` job in `ci.yml`. The job fails when the count rises above `mypy-baseline.txt`, or drops without `--update`. `build` waits for it. Baseline: **50**.
- [x] `mypy.ini`:
  - Merge the duplicate `[mypy]` sections.
  - Pin `platform = linux`, so Windows and CI report the same count.
  - Ignore missing imports only for `fitz` and `pytesseract`.
  - Remove 23 `# type: ignore` comments that mypy reports as unused.
- [x] `tests/test_startup_time.py`:
  - Measure import cost minus interpreter startup, best of 5.
  - Ceiling 1.0 s as a regression guard.
  - The 200 ms target is a strict xfail until Phase 3.
  - Check registration imports once for every heavy package. `segno` and `pyperclip` are strict xfails until Phase 3.
- [x] `release.yml`: install `.[dev,tui]`, **and run `pytest` before publishing**. Before this change it published without running any tests.
- [x] Remove the stale comments in `pyproject.toml`.

**Result:** CI runs pytest and ruff on Python 3.9 to 3.12, and ratcheted mypy (target `python_version = 3.9`) on 3.11. The strict xfails fail loudly when Phase 3 fixes the startup leaks, so their markers get removed.

## Phase 1: Critical bugs (Completed 2026-09-25, branch `fix/hardening-p1-bugs`)

- [x] Every row below has a regression test that failed on the old code before its fix. One commit per bug; 1.3 and 1.4 share a commit, and 1.12 reuses the helper from 1.9.
- [x] New shared helper `common/archives.py` (`safe_extract_tar`), listed in AGENTS.md.
- [x] Results:
  - pytest: 219 → 289 passing.
  - mypy: 50 → 45 errors (baseline updated).
  - Rule audit: 84 → 47 violations. No `py39-union` or `tar-filter` violations remain.
- [x] Found while working:
  - `TestDaemonManager` wrote "Test" tasks into the real `~/.max_cli/tasks/queue.json`. It is now isolated in `tmp_path`; the 23 leftover tasks in the author's queue were not touched.
  - The rule hook's `ruff --fix` deleted imports added before the code that used them. F401 is now unfixable in the hook.
- [x] 1.5 fixed committed code only. The uncommitted `common/download_history.py` keeps its `X | Y` annotations until its author commits it.

| # | Bug | Location | Fix | Test |
|---|---|---|---|---|
| 1.1 | Shred appends random bytes and never overwrites | `core/engines/file_organizer.py:259` (`"ba+"`) | Open with `"r+b"`, and write in chunks for large files | Patch `unlink`, then assert the original bytes are gone from the file |
| 1.2 | Concat list writes a literal `\n`, so every entry lands on one line | `core/engines/media_engine.py:458` | Write `"\n"`, escape `'` in paths, pass `encoding="utf-8"` | The list file has one `file '...'` line per input, including a path containing `'` |
| 1.3 | Queue cancel never removes a PENDING task; a cancelled RUNNING task becomes COMPLETED | `core/engines/daemon_manager.py:101-104, ~280` | Check status before mutating it; `_execute_task` keeps CANCELLED | Both cases |
| 1.4 | Queue mutations and `_save_queue` run outside `_lock`; `except: pass` in `_process_loop` | `daemon_manager.py:255-315, 274` | Hold the lock; log the error and mark the task FAILED | Concurrency test with two threads; a failing executor marks the task FAILED |
| 1.5 | `X \| None` annotations crash on Python 3.9 | `interface/tui/command_executor.py:479`, WIP `common/download_history.py:47,48,83,91` | `Optional[...]` or `from __future__ import annotations` | Enforced by the hook; CI on 3.9 |
| 1.6 | AI-supplied `filename` or `category` can move files outside the target (`../`, absolute paths) | `file_organizer.py:181-201` (`smart_sort`), `ai_engine.categorize_files` | Validate the types, reject separators, require `resolve().is_relative_to(path)` | `../x`, `/abs` and a non-string are each rejected, and nothing moves |
| 1.7 | Plugins auto-run from `./plugins` in the current directory | `plugins/manager.py:50` | Per D2 | A plugin placed in the cwd is not loaded |
| 1.8 | `EventEmitter` calls subscribers while holding a non-reentrant lock, swallows their errors, and fills a queue nothing reads | `common/events.py:125-145` | Copy the subscriber list under the lock and call outside it; log callback errors; bound the queue or remove it if unused | A subscriber that emits no longer deadlocks; memory stays flat over 100k events |
| 1.9 | `ffmpeg_resolver` breaks when `extract_path` is None; `rename` fails on Windows when the target exists | `common/ffmpeg_resolver.py:187,189,197` | Guard the None case; use `Path.replace` | Archive without `extract_path`; target already exists |
| 1.10 | Duplicate finder reads whole files into memory to hash them | `file_organizer.py:111` | Group by size first, then hash in 1 MiB chunks | Same results; a large file is never read whole (patch `read`) |
| 1.11 | `_get_duration` returns 0.0 on every error, which hides a missing ffprobe | `media_engine.py:815-841` | Raise `ProcessingError`, or return `None`, and have callers handle it | ffprobe missing produces a clear error |
| 1.12 | Tar extraction has no filter | `core/engines/network_engine.py:143` | `extractall(canvas_pkg, filter="data")`, with a fallback for Python below 3.12 | Members with `..` are rejected |
| 1.13 | *Confirm first:* `restore_backup` without a target may restore to `~/.max_cli` instead of the original location | `file_organizer.py:~335-360` | Store the original path in the transaction log or backup metadata | Restore lands at the original path |

**Done when:** each row has a regression test that failed before its fix, and pytest, ruff and ratcheted mypy are green.

## Phase 2: Data integrity (Completed 2026-09-25, branch `fix/hardening-p2-data-integrity`)

- [x] `common/atomic.py`: `atomic_write_text` and `atomic_write_json`.
  - They write a temp file next to the target, `fsync` it, then `Path.replace`.
  - On failure they remove the temp file and keep the original.
  - JSON is serialized before any file is opened.
  - Listed in AGENTS.md.
- [x] Every state and config file now writes atomically (17 writes in 12 files):
  - Daemon queue and history, grab queue and history, cache, transaction log, plugin config.
  - AI chat history and export, TUI activity log, ffmpeg path cache, backup sidecars.
  - `.env` and global config (`interface/config/*`, `config_panel.py`), and the `ai extract` JSON export.
  - `tests/test_state_files_atomic.py` breaks `Path.replace` mid-save for six stores. It failed on the old code and passes now.
- [x] Rule hook: a new `atomic-write` rule flags direct `write_text` in `src/`.
  - The only remaining hit is `pdf_engine` OCR output, which is content, not state.
  - The uncommitted `download_history.py` will be flagged when edited.
- [x] utf-8: the audit reports 0 `utf8` violations, down from 23. The rule no longer mistakes `fitz`/PIL/zip/tar/webbrowser `.open()` for text opens.
- [x] Caps: `GRAB_HISTORY_LIMIT` (grab queue), `HISTORY_LIMIT` (daemon, Phase 1), `MAX_ENTRIES` (activity log). Phase 3 merges the stores.
- [x] `ai_engine._get_local_context` uses pathlib, catches only `OSError` and names its 30-file cap. Its tests use a real folder instead of patching `os`.
- [x] Found while working:
  - AI chat export wrote the working directory into `"exported_at"`; it now writes a timestamp.
  - Scripted edits on Windows had stored 14 files with CRLF, including README.md from Phase 1. They are LF again, and `.gitattributes` (`* text=auto eol=lf`) enforces it.
- [ ] Widen `[tool.ruff.lint] select` one family per PR. **Deferred to its own PR:** `I` (import sorting) would rewrite imports in the uncommitted TUI files (`app.py`, `download_panel.py`) and cause merge conflicts. `BLE` alone has 131 findings.
  - `I` (import sorting, auto-fixable)
  - `BLE` (blind excepts)
  - `B`, `UP` (with `FA` for Python 3.9) and `DTZ`
  - The expanded ruff 0.16 defaults flag 784 findings. Those rules stay off for now.
- [x] Results:
  - pytest: 294 → 308.
  - mypy: 45 (unchanged; old and new dependency sets agree).
  - Rule audit: 47 → 25.

## Phase 3: Architecture consolidation (Completed 2026-09-25, branch `refactor/hardening-p3-architecture`)

- [x] **One store (D1).**
  - `max grab`, the TUI download panel and `max queue` share `~/.max_cli/tasks/queue.json` and `history.json`.
  - `task_migration.py` folds `grab_queue.json`, `grab_history.json` and `download_history.json` in on first load, then renames each to `*.migrated`.
  - `queue_manager.py` and `common/download_history.py` are gone. `core/engines/download_history.py` is a view over the store.
  - `get_task_manager()` shares one instance per process, and `refresh()` lets the TUI see other processes' tasks.
  - The maintainer's WIP download panel was committed first (`d956390`), with a fix: `Worker.State` doesn't exist in Textual 8, so its finished and error handlers crashed.
- [x] **Rename the daemon (D3).** `DaemonManager` is now `TaskManager` in `task_manager.py`. The unused PID and log files are gone, and the system panel lists recent tasks instead of `daemon.log`.
- [x] **Remove UI from core.** The audit reports 0 `no-ui-in-core`. Core logs with `logging`, emits a `StatusEvent`, or leaves the message to the interface.
- [x] **Move the FFmpeg prompt to the interface.** The resolver takes `confirm_download` and `on_progress` callbacks. `interface/ffmpeg_prompt.py` supplies them, and without them the resolver raises.
- [x] **Lazy loading.**
  - `core/engines/__init__.py` is empty. `task_queue.EXECUTOR_MODULES` maps each task type to its module, and `get_executor` imports it on first use.
  - `cli_tools` and `cli_queue` use `_get_engine()`.
  - `segno` and `pyperclip` load inside `SystemEngine`, and `generate_qr` returns text instead of printing.
- [x] **Startup (D4).** The event models are dataclasses, and `cli_ai` loads `rich.markdown` lazily. See the results for the remaining gap.
- [x] **Split `media_engine.py`** into `ffmpeg_base.py`, `video_engine.py`, `audio_engine.py` and `stream_engine.py`. `MediaEngine` inherits all three and keeps the executors.
- [x] **Move business logic out of the interface.**
  - `PDFEngine.bundle_pdfs` runs the bundle pipeline, and cleans up its temp file on every path.
  - `ai_engine.download_image` has a 60 s timeout and never leaves a partial file. `find_searchable_files` does the search file discovery.
  - `network_engine.strip_playlist_params` cleans URLs.
- [x] **Narrow the broad catches.** The audit reports 0 silent `except Exception`. Two of them hid bugs:
  - The `max grab` playlist prompt: answering "n" didn't cancel, because the catch swallowed `typer.Exit`.
  - The TUI system panel "Confirm?" buttons never reset, because of a `##btn-...` selector.
- [x] Found while working:
  - Tests now use a temporary task store through an autouse fixture, so they never touch `~/.max_cli`.
  - The download executor passes the playlist options and reports the downloaded files, their size and the video title.
  - `scripts/mypy_baseline.py --update` wrote CRLF on Windows; it writes LF now.

**Done when:**
- [ ] `import max_cli.main` takes under 200 ms. **Not met: about 430 ms** (down from 550 ms). See the results.
- [x] The audit shows 0 `no-ui-in-core`, `lazy-import`, `engine-at-import` and `no-print-in-core` violations.
- [x] One history file exists.
- [x] Every existing CLI command still passes its tests.

**Result:**
- pytest: 357 passed, 1 skipped, 1 xfailed (up from 308).
- mypy: 41 errors, down from 45.
- Rule audit: 25 violations down to 6 (type-ignore-reason 5, atomic-write 1).
- Startup: about 430 ms on the dev machine, measured the same way as `tests/test_startup_time.py`.
  - typer costs about 85 ms.
  - `max_cli.config` costs about 270 ms, most of it pydantic-settings.
  - `cli_images` and `cli_network` read `settings` for option defaults at import time, so config loads during command registration.
  - Reaching 200 ms needs one of two changes, and the maintainer has to choose (**D5** below).

## Decisions needed before closing the startup target

- [ ] **D5. How to reach 200 ms.**
  - Option A: lazy command groups. `max --help` lists the groups without importing them, and each group's module (and `settings`) loads only when you run it. This is the bigger change, and it also speeds up every command.
  - Option B: replace pydantic-settings with a small dataclass plus `.env` loader. This loses pydantic's field validation, and `config_panel` reads `Settings.model_fields`.
  - Option C: raise the target to what's reachable now (about 450 ms) and keep the 1.0 s ceiling.
  - Recommendation: A, as its own small phase before the plugin migration, which needs lazy groups anyway.

## Phase 4: TUI single source of truth (M)

- [ ] Create a `core/presets.py` module (or constants on the engines) for the CRF levels, bitrate maps and other defaults the CLI and TUI share. Today they disagree: the TUI's "max" level is CRF 32 and the CLI's is 35, and the audio bitrate maps differ.
- [ ] `interface/tui/command_executor.py`: import the presets, and move the path derivation and globbing out of `_map_engine_params` (136-308) into engine methods, so that function only maps fields.
- [ ] Add a drift test that asserts the TUI defaults equal the CLI defaults for every shared command.

## Phase 5: Test coverage (L, can run alongside Phases 2-4)

- [ ] Add `CliRunner` tests for the groups that have none: `cli_ai`, `cli_audio`, `cli_files`, `cli_media`, `cli_pdf`, `cli_queue`, `cli_tools`, `cli_config`. Cover at least `--help`, one happy path with a mocked engine, and one `MaxError` path each.
- [ ] Add engine tests for `audio_metadata_engine` and `system_engine`, plus `plugins/manager.py`, `common/cache.py` and `common/retry.py`.
- [ ] Remove the `dummy_image` redefinition in `test_core_images.py`, which shadows the conftest fixture, and add real coverage for compress, resize and convert.
- [ ] Set a coverage floor in CI at the current value, and raise it every phase.

## Phase 6: Docs and PLANS hygiene (S-M)

- [ ] Move the 8 plans marked "Completed" from `PLANS/active/` to `PLANS/completed/`, after reconciling their unticked boxes against the code (`max-plans`).
- [ ] Correct the statuses that don't match the code: `audio-noise-removal` (denoise ships), `grab-media-improvements` (the index says Draft, the file says Completed), and `dashboard-home-analytics-redesign` (`AnalyticsPanel` exists).
- [ ] `README.md`: fix `max share`, `max copy` and `max paste`, which should be `max tools share|copy|paste` (lines 491-497). Add `max queue`, `tools qr`, `pdf ocr/form-*/optimize/compare`, `ai search/extract` and `files duplicates/shred/backup`.
- [ ] Add `docs/commands/queue.md` and `docs/commands/tools.md`, and register both in the `mkdocs.yml` nav.
- [ ] `AGENTS.md`:
  - Remove `ToolsPanel`, which doesn't exist, and add `AnalyticsPanel`.
  - [x] Update the queue/history section after Phase 3 (done in Phase 3).

## Out of scope (tracked elsewhere)

- **Optional heavy dependencies** (openai, yt-dlp, pymupdf, pillow as extras): `plugin_commands_migration.md`. Start it after Phase 3; the lazy-loading cleanup makes it much easier.
- **Real background daemon:** only if D3 picks option B.

## Decisions log

- 2026-09-24: Plan created from the codebase review. Findings came from subagent review, and the major bugs were verified by reading the source.
- 2026-09-24: Phase 0 done.
  - Adding the stub packages exposed 20 hidden errors, and removing stale ignores cleared them again.
  - Measured on the committed tree without local WIP, mypy has 50 errors.
  - The uncommitted `common/download_history.py` adds 4 more (Python 3.9 `X | Y` syntax, Phase 1.5). The gate fails until they are fixed.
- 2026-09-25: CI on PR #2 failed for two reasons, and fail-fast cancelled the other jobs:
  - `mypy>=1.18.0` pulled mypy 2.3.1, which no longer supports `python_version = 3.9`. Capped at `<1.19`.
  - The strict xfail on the 200 ms startup target passed unexpectedly on macOS runners. Timing depends on the machine, so that xfail is now non-strict. The deterministic `segno`/`pyperclip` checks stay strict.
  - CI now runs the test matrix with `fail-fast: false`.
  - After the mypy cap, typecheck still failed. click 8.5 uses `match`, and mypy targeting 3.9 aborted after one error, which the ratchet misread as progress (fixed in `scripts/mypy_baseline.py`). Second strike: HALT, and the maintainer chose `python_version = 3.10`.
  - `--player-client` is now a `str` Enum, because typer 0.27 rejects `click_type=click.Choice`. Old and new dependency sets now report the same 45 errors.
- 2026-09-24: CI on PR #1 failed at `ruff check .`. The unpinned `ruff>=0.1.0` pulled 0.16.8, whose expanded default rules flag 784 findings, and `main` fails the same way. Fixed by pinning the rules to the classic defaults (`E4`, `E7`, `E9`, `F`), setting `target-version = "py39"`, and capping ruff at `>=0.14.6,<0.17`.
- 2026-09-25: Phase 3.
  - The maintainer answered D1 (merge all stores, including the WIP history), D3 (option A) and D4 (keep 200 ms, dataclasses).
  - The dataclass switch alone didn't reach 200 ms: pydantic still loads through `max_cli.config`. Recorded as D5 instead of widening Phase 3.
