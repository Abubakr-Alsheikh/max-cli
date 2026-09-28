"""Catalog entries for `max files`. `tests/test_catalog_drift.py` checks them against the CLI.

The CLI's --force flags skip its own prompts; they have no catalog entry,
because the dashboard and the agent ask according to each action's danger.
"""

from pathlib import Path

from max_cli.core.catalog.spec import Action, Danger, Group, Param, ParamKind

OPS = "max_cli.core.operations.files"


def _dry_run(help: str) -> Param:
    return Param("dry_run", ParamKind.BOOL, help, default=False, cli=("--dry-run",))


GROUP = Group(
    name="files",
    summary="Rename, sort, dedupe, shred and back up files, with undo.",
    actions=(
        Action(
            group="files",
            name="order",
            summary="Put a number in front of every file name (1_report.pdf)."
            " Numbered files are skipped.",
            operation=f"{OPS}:order",
            params=(
                Param("folder", ParamKind.FOLDER, "Folder whose files to number."),
                _dry_run("Show the new names without renaming."),
                Param(
                    "start",
                    ParamKind.INT,
                    "Number to start counting from.",
                    default=1,
                    cli=("--start",),
                ),
            ),
            danger=Danger.MOVES,
        ),
        Action(
            group="files",
            name="smart-sort",
            summary="Let the AI group a folder's files into subfolders by meaning.",
            operation=f"{OPS}:smart_sort",
            params=(
                Param(
                    "path", ParamKind.FOLDER, "Folder to organize.", default=Path(".")
                ),
                _dry_run("Show the moves without moving."),
            ),
            danger=Danger.MOVES,
        ),
        Action(
            group="files",
            name="duplicates",
            summary="Find files with identical content; optionally delete the extra"
            " copies (backed up for undo).",
            operation=f"{OPS}:duplicates",
            params=(
                Param(
                    "folder",
                    ParamKind.FOLDER,
                    "Folder to scan.",
                    default=Path("."),
                ),
                Param(
                    "recursive",
                    ParamKind.BOOL,
                    "Scan subfolders too.",
                    default=False,
                    cli=("-r", "--recursive"),
                ),
                Param(
                    "delete",
                    ParamKind.BOOL,
                    "Delete the duplicates, keeping one copy of each.",
                    default=False,
                    cli=("-d", "--delete"),
                ),
            ),
            danger=Danger.DELETES,
        ),
        Action(
            group="files",
            name="shred",
            summary="Destroy a file for good: overwrite it with random data, then"
            " delete it. No backup, no undo.",
            operation=f"{OPS}:shred",
            params=(
                Param("target", ParamKind.FILE, "File to destroy."),
                Param(
                    "passes",
                    ParamKind.INT,
                    "Times to overwrite the file.",
                    default=3,
                    cli=("--passes", "-p"),
                    advanced=True,
                ),
            ),
            danger=Danger.DELETES,
        ),
        Action(
            group="files",
            name="preview",
            summary="Show a file's details and the start of its content.",
            operation=f"{OPS}:preview",
            params=(
                Param("target", ParamKind.FILE, "File to look at."),
                Param(
                    "lines",
                    ParamKind.INT,
                    "Lines to show for a text file.",
                    default=20,
                    cli=("-n", "--lines"),
                ),
            ),
            danger=Danger.NONE,
        ),
        Action(
            group="files",
            name="backup",
            summary="Save a copy of a file in ~/.max_cli/backups.",
            operation=f"{OPS}:backup",
            params=(
                Param("target", ParamKind.FILE, "File to back up."),
                Param(
                    "label",
                    ParamKind.TEXT,
                    "Word added to the backup's name.",
                    default="manual",
                    cli=("-l", "--label"),
                ),
            ),
        ),
        Action(
            group="files",
            name="backups",
            summary="List your backups, or restore one.",
            operation=f"{OPS}:backups",
            params=(
                Param(
                    "filter",
                    ParamKind.TEXT,
                    "Only backups whose name contains this.",
                    default=None,
                    cli=("--filter", "-f"),
                ),
                Param(
                    "restore",
                    ParamKind.FILE,
                    "Backup file to restore.",
                    default=None,
                    cli=("--restore", "-r"),
                ),
                Param(
                    "output",
                    ParamKind.FOLDER,
                    "Folder to restore into. Default: where the file came from.",
                    default=None,
                    cli=("-o",),
                    advanced=True,
                ),
            ),
        ),
        Action(
            group="files",
            name="backup-cleanup",
            summary="Delete backups older than a number of days.",
            operation=f"{OPS}:backup_cleanup",
            params=(
                Param(
                    "days",
                    ParamKind.INT,
                    "Remove backups older than this many days.",
                    default=30,
                    cli=("-d", "--days"),
                ),
            ),
            danger=Danger.DELETES,
        ),
        Action(
            group="files",
            name="undo",
            summary="Undo the last rename, move or delete that Max recorded.",
            operation=f"{OPS}:undo",
            params=(),
            danger=Danger.MOVES,
        ),
        Action(
            group="files",
            name="history",
            summary="List recent file operations you can undo.",
            operation=f"{OPS}:history",
            params=(
                Param(
                    "limit",
                    ParamKind.INT,
                    "How many to show.",
                    default=10,
                    cli=("-n", "--limit"),
                ),
                Param(
                    "verbose",
                    ParamKind.BOOL,
                    "Show each step.",
                    default=False,
                    cli=("-v", "--verbose"),
                ),
            ),
            danger=Danger.NONE,
        ),
    ),
)
