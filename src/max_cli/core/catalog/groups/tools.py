"""Catalog entries for `max tools`. `tests/test_catalog_drift.py` checks them against the CLI."""

from max_cli.core.catalog.spec import Action, Danger, Group, Param, ParamKind

OPS = "max_cli.core.operations.tools"

GROUP = Group(
    name="tools",
    summary="Small helpers: a QR code for a link, the clipboard.",
    actions=(
        Action(
            group="tools",
            name="share",
            guide=(
                "Use for: sending a link or a short text to a phone: it shows a QR "
                "code to scan."
            ),
            summary="Show a QR code for a link or text, to open it on your phone.",
            operation=f"{OPS}:share",
            params=(Param("data", ParamKind.TEXT, "Text or link to put in the code."),),
            danger=Danger.NONE,
        ),
        Action(
            group="tools",
            name="paste",
            guide=(
                "Use for: saving a screenshot or an image on the clipboard as a "
                "file. How: output names the file."
            ),
            summary="Save the image on your clipboard, such as a screenshot, to a file.",
            operation=f"{OPS}:paste",
            params=(
                Param(
                    "output",
                    ParamKind.OUTPUT,
                    "File to save. Max adds .png when you leave off the extension.",
                    default="clipboard.png",
                ),
                # An option, not a --force: the file is replaced only when
                # you ask, so the dashboard has nothing to confirm.
                Param(
                    "overwrite",
                    ParamKind.BOOL,
                    "Replace a file that already has this name.",
                    default=False,
                    cli=("-f", "--force"),
                ),
            ),
        ),
        Action(
            group="tools",
            name="copy",
            guide=(
                "Use for: putting a text file's contents on the clipboard, to paste "
                "somewhere else."
            ),
            summary="Copy a text file's contents to the clipboard.",
            operation=f"{OPS}:copy",
            params=(Param("target", ParamKind.FILE, "Text file to copy."),),
            danger=Danger.NONE,
        ),
    ),
)
