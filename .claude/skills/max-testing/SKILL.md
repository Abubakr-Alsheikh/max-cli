---
name: max-testing
description: How to write and run tests in Max CLI - fixtures, mocking lazy imports, FFmpeg/network/AI mocks, CliRunner setup, Textual TUI tests, and the bug-regression pattern. Use when adding or fixing tests, when a test fails, or before claiming a change works.
---

# Testing Max CLI

## Commands
```bash
pytest                                  # full suite (~15s)
pytest tests/test_core_media.py -k concat
pytest --cov=max_cli --cov-report=term-missing
ruff check . && mypy <changed files>
```

## Layout
- Engine tests go in `tests/test_core_<engine>.py`. Instantiate the engine directly and assert on the return values and the file state.
- CLI tests go in `tests/test_cli_<group>.py`. Use `typer.testing.CliRunner` and assert on the exit code and stdout.
- TUI tests go in `tests/interface/tui/`. Use the Textual Pilot API (`async with app.run_test() as pilot`), with `pytest-asyncio`.
- Utility tests go in `tests/test_<module>.py` for `common/` modules.

## Fixtures (`tests/conftest.py`): use these, don't make ad-hoc files
`temp_directory`, `dummy_image`, `dummy_image_png`, `dummy_pdf`, `dummy_pdf_multi`, `dummy_video`, `dummy_audio`, `sample_files`, `sample_directory`, `mock_env_vars`. Don't redefine them in test modules; shadowing them hides fixture changes.

## CliRunner
Rich wraps help text to the terminal width and adds ANSI codes, which breaks substring asserts. Always build the runner like this:
```python
runner = CliRunner(env={"NO_COLOR": "1", "TERM": "dumb", "COLUMNS": "200"})
```
Patch the interface's `_get_engine` to isolate the CLI layer:
```python
@patch("max_cli.interface.cli_media._get_engine")
def test_compress(mock_get_engine, dummy_video): ...
```

## Mocking rules
- **Lazy imports: patch the package, not the engine module.** Use `@patch("openai.OpenAI")`, not `@patch("max_cli.core.engines.ai_engine.OpenAI")`. The same applies to `yt_dlp.YoutubeDL` and `fitz.open`.
- **AIEngine:** set `engine._client = mock_client`, because `client` is a lazy property.
- **FFmpeg:** mock `subprocess.run` and `shutil.which`. Assert on the argument list you built (`mock_run.call_args[0][0]`), including `str(engine.ffmpeg_path)` as element 0.
- **Network:** no test may make a real network call. Mock `requests` / `yt_dlp` / `openai`.
- **Home directory state:** point `Path.home()` or the module's state-dir constant at `tmp_path` with `monkeypatch`. Tests must never write to the real `~/.max_cli`.

## Regression test pattern for bug fixes
Every bug fix gets a test that fails before the fix and passes after it. Write the test first, run it, and watch it fail for the right reason. Examples from known bugs:
- **shred:** after `secure_delete`, the file is gone. Patch `unlink` and assert that the original bytes no longer appear in the file.
- **concat list:** the list file has one `file '...'` entry per line.
- **queue cancel:** a PENDING task disappears from the queue, and a cancelled RUNNING task stays CANCELLED.
- **AI path traversal:** a category of `../x` or an absolute path is rejected, and nothing moves outside the target.

## Python 3.9
CI runs Python 3.9 to 3.12. Tests must import on 3.9 too: no `X | Y` annotations without `from __future__ import annotations`, and no `match` statements.

## When a test fails
Read the full assertion and traceback before changing anything. Fix the root cause, not the assertion. After two failed fix attempts, stop and report a `[HALT]` with your hypotheses (AGENTS.md section 19).
