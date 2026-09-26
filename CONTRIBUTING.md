# Contributing to Max CLI

Welcome to Max CLI! This guide will help you get started with development.

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

- Follow PEP 8 with 88 character line length (configured in pyproject.toml)
- Use type hints for all function signatures
- Use import organization: stdlib → third-party → local (sorted alphabetically)
- Run ruff format before committing

## Naming Conventions

- Classes: PascalCase (e.g., `ImageEngine`)
- Functions/Variables: snake_case (e.g., `process_single_image`)
- Constants: UPPER_SNAKE_CASE (e.g., `DEFAULT_QUALITY`)
- Private methods: Prefix with underscore (e.g., `_resolve_batch`)

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

# Full (about 4 minutes): the tests on Python 3.9, 3.10, 3.11 and 3.12 in fresh virtualenvs,
# two at a time, plus the package build. A step that hangs stops after 10 minutes.
# Needs uv, which downloads any Python you don't have.
python scripts/ci_local.py --full

# Once per clone: make `git push` run the quick check on commits that haven't passed yet
python scripts/ci_local.py --install-hook
```

CI also runs on macOS and Linux. The script can't reproduce those, so watch for file-order and path differences.

## Submitting PRs

1. Create a feature branch:

   ```bash
   git checkout -b feature/your-feature-name
   ```

2. Make your changes and run quality checks:

   ```bash
   ruff format .
   python scripts/ci_local.py --full
   ```

3. Commit with a clear message:

   ```bash
   git commit -m "Add feature: description"
   ```

4. Push and create a PR:

   ```bash
   git push origin feature/your-feature-name
   ```

## Project Structure

```
src/max_cli/
├── core/           # Business logic engines
├── interface/     # Typer CLI commands
├── common/        # Shared utilities
├── config.py      # Configuration settings
└── main.py        # CLI entry point
```

## Common Development Tasks

### Adding a New Engine Command

1. Create or update engine in `src/max_cli/core/`
2. Add CLI command in `src/max_cli/interface/`
3. Add tests in `tests/`

### Adding Configuration

- Edit `src/max_cli/config.py`
- Add new Settings fields with pydantic Field validation

## Getting Help

- Open an issue: <https://github.com/your-repo/max-cli/issues>
- Check existing issues and discussions
