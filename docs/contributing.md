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

## Submitting PRs

1. Create a feature branch
2. Make changes and run quality checks
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
