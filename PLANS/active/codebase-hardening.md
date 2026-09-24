# Plan: Codebase Hardening

**Status:** In Progress (Phases 0-1 done)
**Priority:** P0
**Updated:** 2026-09-24

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

- [ ] **D1. One queue and history store.**
  - Merge the `max grab` queue (`QueueManager`, `~/.max_cli/grab_history.json`) into `DaemonManager` + `task_queue` (`~/.max_cli/queue/history.json`)?
  - Fold the uncommitted `common/download_history.py` into that store instead of adding a third file?
  - Recommendation: yes to both. Put one persistence helper under `DaemonManager`, and migrate the old files on first load.
- [x] **D2. Plugin loading from `./plugins`.** Decided 2026-09-24: home directory only. Extra folders come from `"plugin_dirs"` in `~/.max_cli/plugins.json` (implemented in 1.7).
- [ ] **D3. The "daemon".**
  - It's a `daemon=True` thread that dies when the CLI exits.
  - Option A: rename it to an in-process worker and remove the unused PID and log files.
  - Option B: build a real detached background process.
  - Recommendation: A now, and B as its own plan if it's ever needed.
- [ ] **D4. Startup target.**
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

## Phase 2: Data integrity (M)

- [ ] Add a `common/atomic.py` helper: `atomic_write_text(path, text)` and `atomic_write_json(path, data)`. They write a temp file in the same directory, `fsync` it, then `Path.replace`. Check `common/` first so this doesn't duplicate an existing helper.
- [ ] Use the helper for every state file:
  - `daemon_manager` (queue and history)
  - `queue_manager`
  - `common/cache.py`
  - `common/transaction_log.py:73`
  - `plugins/manager.py`
  - `ai_engine` chat history
- [ ] Pass `encoding="utf-8"` to the 26 text-mode opens the audit lists: `queue_manager.py:148,165,196,206`, `cache.py:36,55,94`, `ffmpeg_resolver.py:220,227`, `plugins/manager.py:63,73`, and others.
- [ ] Replace the magic history caps (200, 100, 200) with named constants. Phase 3 makes them a single constant.
- [ ] Replace `os.listdir` and `os.getcwd` in `ai_engine.py:115-118` with pathlib.
- [ ] Widen `[tool.ruff.lint] select` one family per PR, fixing each family's findings as you go:
  - `I` (import sorting, auto-fixable)
  - `BLE` (blind excepts)
  - `B`, `UP` (with `FA` for Python 3.9) and `DTZ`
  - The expanded ruff 0.16 defaults flag 784 findings. Those rules stay off for now.

**Done when:** `check_rules.py --audit` reports 0 `utf8` violations and a crash mid-write can't corrupt any JSON state file (tested by patching `replace` to raise).

## Phase 3: Architecture consolidation (L, needs D1-D4)

- [ ] **One store.** Per D1, move `max grab` queueing onto `DaemonManager` + `task_queue`, migrate `grab_history.json` and `download_history.json` on first load, then delete `queue_manager.py` and fold `download_history.py` into that store.
- [ ] **Remove UI from core.** Replace the `console` usage in `daemon_manager.py:9,59,79,258`, `queue_manager.py`, and `media_engine.py:406,850` with events or return values.
- [ ] **Move the FFmpeg prompt to the interface.** `ffmpeg_resolver` must not call `Confirm.ask`. It takes an `on_confirm` callback that the interface supplies, or raises, and the interface asks.
- [ ] **Lazy loading.**
  - Empty `core/engines/__init__.py` of eager engine imports, and register task executors explicitly (not as an import side effect).
  - Replace the module-level `engine = SystemEngine()` (`cli_tools.py:8`) and `daemon = DaemonManager()` (`cli_queue.py:11`) with `_get_engine()` helpers.
  - Lazy-load `segno` and `pyperclip` inside `system_engine` methods.
  - Remove the `print` calls at `system_engine.py:17,19`.
- [ ] **Startup (D4).** Switch `common/events.py` models from pydantic to `dataclasses`. Target: `import max_cli.main` under 200 ms, enforced by the Phase 0 test.
- [ ] **Split `media_engine.py` (1090 lines)** by domain: `video_engine.py`, `audio_engine.py` (to-audio, denoise and the rnnoise model), `stream_engine.py` (the HTTP server). Keep a thin `MediaEngine` facade until every caller has moved.
- [ ] **Move business logic out of the interface.**
  - `cli_ai.py`: move the image download (186-205, which has no timeout) and the file discovery (327) into engines.
  - `cli_pdf.py`: move the bundle pipeline (209-253), including its `os.remove` calls, into `PDFEngine`.
  - `cli_network.py`: move the URL cleaning (36-55) into `NetworkEngine`.
- [ ] **Narrow the broad catches.** Replace the silent `except Exception` blocks the audit lists with specific exceptions, or log them. Start with `ai_engine.py:57,108,127,249,512`, `network_engine.py:145` and `plugins/manager.py:65`.

**Done when:**
- `import max_cli.main` takes under 200 ms.
- The audit shows 0 `no-ui-in-core`, `lazy-import`, `engine-at-import` and `no-print-in-core` violations.
- One history file exists.
- Every existing CLI command still passes its tests.

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
  - Update the queue/history section after Phase 3.

## Out of scope (tracked elsewhere)

- **Optional heavy dependencies** (openai, yt-dlp, pymupdf, pillow as extras): `plugin_commands_migration.md`. Start it after Phase 3; the lazy-loading cleanup makes it much easier.
- **Real background daemon:** only if D3 picks option B.

## Decisions log

- 2026-09-24: Plan created from the codebase review. Findings came from subagent review, and the major bugs were verified by reading the source.
- 2026-09-24: Phase 0 done.
  - Adding the stub packages exposed 20 hidden errors, and removing stale ignores cleared them again.
  - Measured on the committed tree without local WIP, mypy has 50 errors.
  - The uncommitted `common/download_history.py` adds 4 more (Python 3.9 `X | Y` syntax, Phase 1.5). The gate fails until they are fixed.
- 2026-09-24: CI on PR #1 failed at `ruff check .`. The unpinned `ruff>=0.1.0` pulled 0.16.8, whose expanded default rules flag 784 findings, and `main` fails the same way. Fixed by pinning the rules to the classic defaults (`E4`, `E7`, `E9`, `F`), setting `target-version = "py39"`, and capping ruff at `>=0.14.6,<0.17`.
