# Contributing

## Development Setup

1. Fork and clone the repository:

   ```bash
   git clone https://github.com/Abubakr-Alsheikh/max-cli.git
   cd max-cli
   ```

2. Create a virtual environment:

   ```bash
   python -m venv .venv
   source .venv/bin/activate  # Linux/macOS
   .venv\Scripts\activate     # Windows
   ```

3. Install dev dependencies:

   ```bash
   pip install -e .[dev]
   ```

## Code Style

- Follow PEP 8 with 88 character line length
- Use type hints for all function signatures
- Run `ruff format` before committing

## Running Tests

```bash
# Run all tests
pytest

# Run specific test file
pytest tests/test_core_images.py

# Run with coverage
pytest --cov=max_cli
```

## Running Linters

```bash
# Check code style
ruff check .

# Format code
ruff format .

# Type check: the error count may not rise above mypy-baseline.txt
python scripts/mypy_baseline.py
```

After you fix type errors, run `python scripts/mypy_baseline.py --update` to lock in the lower count.

## Running CI Locally

`scripts/ci_local.py` runs the checks from `.github/workflows/ci.yml` on your machine, so a push doesn't fail on GitHub for a reason you could have caught first.

```bash
# Default (1-3 minutes): ruff, the mypy ratchet, every module imported on Python 3.9,
# and only the tests that cover the files changed since main. A change to
# pyproject.toml or a conftest.py runs the whole suite.
python scripts/ci_local.py

# Quick: the whole suite on this Python with the 70% coverage floor (about 10 minutes)
python scripts/ci_local.py --quick

# Full (about 20 minutes): the whole suite on Python 3.9, 3.10, 3.11 and 3.12 in fresh
# virtualenvs, two at a time, plus the package build. Needs uv, which downloads any
# Python you don't have. Its first run also makes the 3.9 virtualenv the default check uses.
python scripts/ci_local.py --full

# Short of memory? Run the Python versions one at a time (slower)
CI_LOCAL_PARALLEL=1 python scripts/ci_local.py --full

# Once per clone: make `git push` run the default check on commits that haven't passed yet
python scripts/ci_local.py --install-hook
```

GitHub CI runs the whole suite on every Python and system for every PR, so the default check is enough before you push: it catches what you broke in the files you touched, in a few minutes.

CI also runs on macOS and Linux. The script can't reproduce those, so watch for file-order and path differences.

## Agent evals

`scripts/agent_eval.py` asks the AI agent set requests with your configured AI model and scores what it chose: one batch call instead of a call per file, a plan before multi-step work, looking before advising, saving a fact it was told.

```bash
python scripts/agent_eval.py               # every scenario
python scripts/agent_eval.py --only batch  # one of them
python scripts/agent_eval.py --list
```

Each scenario runs in dry-run mode in a temporary folder, with Max's activity log and the agent's notes in a temporary home, so nothing of yours changes. It costs a few model requests per run, and models vary from run to run: run it twice before you trust a change to the agent's prompt or tools. Add a scenario to `SCENARIOS` when you fix a choice the agent got wrong.

## Submitting PRs

1. Create a feature branch
2. Make changes. If they touch the package (`src/` or `pyproject.toml`), run `python scripts/ci_local.py` (1-3 minutes) before the PR. Docs, tests and scripts can go straight to the PR. GitHub CI tests every PR on every Python, and its checks must pass before a merge.
3. Commit with a Conventional Commits message (see below)
4. Push and create a PR

## Commit Messages

Start every commit with its type, an optional scope and a colon: `feat(images): convert SVG`. The type decides which release the change needs:

| Type | Use it for | Release |
|------|------------|---------|
| `feat` | Something new you can use: a command, an option, a page, a setting, a format | minor |
| `fix` | A bug fixed | patch |
| `perf` | The same result, faster or lighter | patch |
| `docs`, `test`, `refactor`, `style`, `ci`, `build`, `chore` | Nothing users notice | none |

Mark a change that breaks something users rely on with `!` after the type (`feat(cli)!: rename max grab to max get`), or a `BREAKING CHANGE:` line in the body that says what breaks and what to do instead.

## Versions and Releases

Max follows [Semantic Versioning](https://semver.org): `MAJOR.MINOR.PATCH`. A release takes the biggest change since the last one.

**Major** (`1.4.2` to `2.0.0`): something that worked stops working, or works differently, without you changing anything.

- A command, an option or a setting is removed or renamed (`config.REMOVED_SETTINGS` grows).
- A default changes what a command makes: output names, folders, formats, quality.
- A Python version is dropped (`requires-python` changes).
- Exit codes that scripts check change.
- The plugin API (`max_cli.plugins.base`) changes in a way old plugins can't follow.

**Minor** (`1.4.2` to `1.5.0`): something new, and everything old still works.

- A new command, option, dashboard page, setting, file format or AI provider.
- A new Python version supported, or a new dependency that installs by itself.
- Something marked as going away in a later major release (the old way still works).

**Patch** (`1.4.2` to `1.4.3`): fixes only.

- Bugs, crashes, wrong results, slow paths.
- Wording, docs and tests that ship with a fix.

**No release**: only docs, tests, refactors or CI changed. Wait for a fix or a feature.

When you're unsure between two levels, take the bigger one: a surprise costs users more than a version number.

To see what the next release should be:

```bash
python scripts/release_plan.py           # since the last tag
python scripts/release_plan.py --since v1.0.0
```

It sorts the commits since the last tag by type, flags a dropped Python version or removed settings, and prints the suggested level and version with the commits behind it. It suggests; you decide.

### Making a release

1. Run `python scripts/release_plan.py` and agree on the level.
2. On a `release/X.Y.Z` branch, set `version` in `pyproject.toml` and add a `## X.Y.Z (date)` section at the top of `CHANGELOG.md` with **New**, **Fixed** and **Changed** lists written for users, not copied from commits. Say what to do for every breaking change.
3. Run `python scripts/ci_local.py --full`, open the PR and merge it once GitHub's checks pass.
4. On the merged `main`, tag the merge commit and push the tag: `git tag -a vX.Y.Z -m "Max X.Y.Z"` and `git push origin vX.Y.Z`.
5. The Release workflow tests again, builds, creates the GitHub release with the CHANGELOG section as its notes and publishes to PyPI. Check that https://pypi.org/project/max-cli/ shows the new version.
6. In an editable install, run `pip install -e . --no-deps` (with the dashboard closed) so `max --version` and the sidebar show the new version.

## Project Structure

```
src/max_cli/
├── core/
│   ├── catalog/      # one description per action (params, defaults, danger, batches)
│   ├── operations/   # the work behind each action; returns an ActionResult
│   ├── engines/      # FFmpeg, PDF, images, AI providers, downloads, the task queue
│   ├── agent/        # the AI agent
│   └── cli/          # lazy command-group loading
├── interface/        # Typer commands (cli_*.py) and the dashboard (tui/)
├── common/           # shared helpers
├── plugins/          # plugin system
└── config.py         # settings
```

A new command touches three places: its catalog entry, its operation and its CLI command. `tests/test_catalog_drift.py` fails when they disagree. [AGENTS.md](https://github.com/Abubakr-Alsheikh/max-cli/blob/main/AGENTS.md) lists the patterns and rules, and [API Reference](api/index.md) shows the layers.
