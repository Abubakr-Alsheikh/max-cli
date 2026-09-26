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

# Type check
mypy src/
```

## Running CI Locally

`scripts/ci_local.py` runs the checks from `.github/workflows/ci.yml` on your machine, so a push doesn't fail on GitHub for a reason you could have caught first.

```bash
# Quick: ruff, the mypy ratchet, and the tests with the 70% coverage floor (about 2 minutes)
python scripts/ci_local.py

# Full: the tests on Python 3.9, 3.10, 3.11 and 3.12 in fresh virtualenvs, plus the package build.
# Needs uv, which downloads any Python you don't have.
python scripts/ci_local.py --full

# Once per clone: make `git push` run the quick check on commits that haven't passed yet
python scripts/ci_local.py --install-hook
```

CI also runs on macOS and Linux. The script can't reproduce those, so watch for file-order and path differences.

## Submitting PRs

1. Create a feature branch
2. Make changes, then run `python scripts/ci_local.py --full`
3. Commit with a clear message
4. Push and create a PR

## Project Structure

```
src/max_cli/
├── core/           # Business logic engines
├── interface/     # Typer CLI commands
├── common/        # Shared utilities
├── plugins/       # Plugin system
└── config.py      # Configuration
```
