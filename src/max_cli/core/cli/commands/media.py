from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typer import Typer

from max_cli.interface import cli_images, cli_media


def register(app: "Typer") -> None:
    """Register media processing commands (images, video)."""
    app.add_typer(
        cli_images.app, name="images", help="Compress, resize, and convert images."
    )
    app.add_typer(cli_images.app, name="img", hidden=True)

    app.add_typer(
        cli_media.app, name="video", help="Compress, convert, and process video/audio."
    )
    app.add_typer(cli_media.app, name="v", hidden=True)
