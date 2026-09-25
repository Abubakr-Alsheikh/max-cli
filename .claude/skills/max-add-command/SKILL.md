---
name: max-add-command
description: End-to-end checklist for adding or changing a Max CLI command, flag, or engine method (engine, Typer interface, registration, TUI registry, tests, docs, PLANS). Use whenever the task adds a new `max ...` command, a new option on an existing command, or a new Core Engine.
---

# Add or change a Max CLI command

Work through these steps in order. Skip a step only when it does not apply, and name the skipped step in the final report.

## 1. Read before writing
- Read `AGENTS.md` sections 4, 6 and 20. Read the target `interface/cli_<group>.py` and its engine in full.
- Search `src/max_cli/common/` for an existing helper before writing a new one. Check `format_size`, `retry`, `cache`, `process_batch_parallel`, `transaction_log`, `events` and `ffmpeg_resolver`.
- Check `PLANS/active/` for a plan covering this feature.
- Find the right group: images → `cli_images.py`, video → `cli_media.py`, audio tags → `cli_audio.py`, PDF → `cli_pdf.py`, file ops → `cli_files.py`, downloads → `cli_network.py`, LLM → `cli_ai.py`, small utils → `cli_tools.py`, background jobs → `cli_queue.py`.

## 2. Engine (`src/max_cli/core/engines/`)
- Put the logic in an engine method. It takes Python values or `Path` and returns data: a dict, a dataclass, a `Path`, or a stats object.
- The engine must not use `print`, `typer`, `rich`, `console`, or `Confirm`. Report progress with `get_emitter()` events from `max_cli.common.events`.
- Import heavy packages (PIL, fitz, yt_dlp, openai, mutagen, requests, segno, pyperclip) **inside the method**.
- Build every subprocess call as an argument list with `str(self.ffmpeg_path)`. Never use `shell=True`.
- Use `pathlib` only, and pass `encoding="utf-8"` to every text read and write.
- **Writes must be atomic.** Write to a temp file in the same directory, then call `Path.replace()`. JSON state files follow the same rule.
- **Destructive operations:**
  - Accept an optional `transaction_log` parameter and record the operation before you mutate anything.
  - Take a backup before a delete.
- **AI output is untrusted.** Validate its types and use `.get()` with defaults. Any path the AI returns must resolve inside the target directory (`resolved.is_relative_to(base)`).
- Raise `MaxError` subclasses from `max_cli.common.exceptions`. Don't return error strings.
- Type-hint everything, and keep it compatible with Python 3.9. Write `Optional[X]` / `Union[X, Y]` unless the module has `from __future__ import annotations`. No `match` statements.

## 3. Interface (`src/max_cli/interface/cli_<group>.py`)
- Get the engine through a module `_get_engine()` helper. Never create an engine at import time, and never import an engine from another CLI module.
- Give every option a smart default. Pull defaults from `max_cli.config.settings` when a setting exists.
- Keep command bodies to argument parsing, the engine call, and Rich output (`console`, `log_success`, `log_error`).
- Wrap the call in `try/except MaxError`, then call `log_error` and `raise typer.Exit(1)`. The user must never see a stack trace.
- Destructive commands need `Confirm.ask()`, with a `--force/-f` flag to skip it.
- Long-running commands get a `--queue` flag that enqueues a `TaskItem` through `TaskManager`.
- Show progress with `EventSubscriber` from `max_cli.interface.event_subscriber`. Don't pass Rich objects into core.

## 4. Registration
- A new group is one `LazyGroupSpec` entry in `_GROUPS` in `src/max_cli/core/cli/registry.py` (module path, help line, `hidden=True` for aliases). The group's module loads only when someone runs it, so never import `interface` modules at module level in `registry.py` or `main.py`. `tests/test_lazy_groups.py` checks that every entry loads. A new command in an existing group needs no registration.
- Run `max <group> --help` and `max <group> <cmd> --help` and read the output.

## 5. TUI (only if the command should appear in `max dashboard`)
- Add a `CommandSchema` in `src/max_cli/interface/tui/command_registry.py`, and add its parameter mapping in `command_executor.py`.
- **Import presets from the CLI or engine constants instead of copying them.** CRF and bitrate maps have already drifted between the TUI and the CLI.

## 6. Tests
Follow the `max-testing` skill. At minimum you need:
- One engine test for the happy path.
- One engine test for a failure or edge case.
- One `CliRunner` test for the command.

## 7. Docs
- Add the command and an example to `README.md`.
- Update `docs/commands/<group>.md`. A new group needs a new page, and that page must be added to the `nav` in `mkdocs.yml`.
- Update `AGENTS.md` only for a new engine, a new `common/` utility, or a new pattern.

## 8. Finish
- `pytest`, `ruff check .` and `mypy <changed files>` must be clean. The Stop hook runs ruff + pytest automatically.
- Update the relevant `PLANS/active/*.md` checkboxes (see `max-plans`).
- End the report with: "Documentation has been synchronized."
