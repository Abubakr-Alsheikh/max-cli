# Max CLI

The AI-powered CLI companion for high-performance tasks.

## Installation

To install Max CLI, navigate to the project root directory and run the following command:

```bash
cd max-cli
pip install -e .
```

This will install the `max` command into your Python environment, making it accessible from any terminal window.

## Usage Examples

*   **Compress Images:** `max images compress ./VacationPhotos -q 70 --jpeg`
*   **Order Files:** `max files order ./documents`
*   **AI Copilot:** `max ai ask "Please make all images in this folder smaller"`
*   **Get Help:** `max --help` (Auto-generated documentation for all commands and subcommands)

## Project Structure

This project follows a Modular Monolith design, separating business logic from the command-line interface.

-   `pyproject.toml`: Project metadata and dependencies.
-   `src/max_cli/config.py`: Global configuration settings.
-   `src/max_cli/common/logger.py`: Centralized logging utilities.
-   `src/max_cli/core/`: Contains core business logic (e.g., `image_processor.py`, `file_organizer.py`).
-   `src/max_cli/interface/`: Defines CLI commands using Typer (e.g., `cli_images.py`, `cli_files.py`, `cli_ai.py`).
-   `src/max_cli/main.py`: The main entry point for the `max` command.

## Adding New Commands

To add a new command:

1.  Create a new Python file in `src/max_cli/core/` for the business logic.
2.  Create a corresponding CLI interface file in `src/max_cli/interface/` using `typer`.
3.  Register the new `typer` app in `src/max_cli/main.py`.
