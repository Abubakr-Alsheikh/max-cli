import sys

import typer

from max_cli.interface.config import grab_app, manage_app, setup_app

app = typer.Typer(help="Manage API keys and settings.")

# Mount the sub-apps without a name so their commands sit directly under
# `max config` (`max config show`). A name made each one a nested group, so
# only `max config show show` worked.
app.add_typer(setup_app)
app.add_typer(grab_app)
app.add_typer(manage_app)


@app.command("setup-font")
def setup_font(
    yes: bool = typer.Option(False, "--yes", "-y", help="Don't ask; do every step."),
    force: bool = typer.Option(
        False, "--force", "-f", help="Download the font again even if it's installed."
    ),
):
    """Install a Nerd Font for the dashboard's page icons, and offer to make
    it Windows Terminal's font."""
    from rich.prompt import Confirm

    from max_cli.common import terminal_font as fonts
    from max_cli.common.exceptions import MaxError
    from max_cli.common.logger import console, log_error, log_success

    if not yes and not sys.stdin.isatty():
        # `! max config setup-font` and pipes have no keyboard: the questions
        # read end-of-input and stopped with a bare "Aborted."
        log_error(
            "This command asks before it downloads or changes anything, and nothing "
            "here can answer. Run it in a terminal, or add --yes."
        )
        raise typer.Exit(1)
    if fonts.font_installed() and not force:
        console.print(f"[green]{fonts.NERD_FONT_FACE} is installed.[/green]")
    else:
        ask = (
            f"Download {fonts.NERD_FONT_FACE} ({fonts.NERD_FONT_SIZE_TEXT}, SIL Open "
            "Font License) from github.com/ryanoasis/nerd-fonts and install it "
            "for your user?"
        )
        if not yes and not Confirm.ask(ask, default=True):
            console.print("[dim]Cancelled.[/dim]")
            return
        try:
            with console.status("Downloading the font..."):
                folder = fonts.setup_font()
        except (MaxError, OSError) as e:
            log_error(f"Font setup failed: {e}")
            raise typer.Exit(1) from None
        log_success(f"Installed {fonts.NERD_FONT_FACE} in {folder}")

    settings_path = fonts.terminal_settings_path()
    if settings_path is None:
        console.print(
            f"Set [bold]{fonts.NERD_FONT_FACE}[/bold] as your terminal's font, then "
            "pick [bold]Nerd Font[/bold] for Page icons on the dashboard's Settings page."
        )
        return
    current = fonts.terminal_font_face(settings_path)
    if fonts.is_nerd_face(current):
        log_success(f"Windows Terminal already uses a Nerd Font ({current}).")
        return
    if not yes and not Confirm.ask(
        f"Make {fonts.NERD_FONT_FACE} Windows Terminal's font? Max keeps a copy of "
        "its settings first.",
        default=True,
    ):
        console.print(
            "[dim]Windows Terminal keeps its font. Set it under Settings > Defaults "
            "> Appearance > Font face.[/dim]"
        )
        return
    try:
        backup = fonts.set_terminal_font(path=settings_path)
    except (MaxError, OSError) as e:
        log_error(str(e))
        raise typer.Exit(1) from None
    log_success(
        "Windows Terminal now uses the font. Open a new tab, then run max: the "
        "pages have their icons."
    )
    console.print(f"[dim]The old settings are in {backup}[/dim]")


@app.command("setup-ffmpeg")
def setup_ffmpeg(
    force: bool = typer.Option(False, "--force", "-f", help="Force re-download"),
):
    """Download and install FFmpeg binary to ~/.max_cli/bin/."""
    from max_cli.common.ffmpeg_resolver import FFmpegResolver, resolve_ffmpeg
    from max_cli.common.logger import console, log_error, log_success
    from max_cli.interface.ffmpeg_prompt import ffmpeg_prompt_callbacks

    resolver = FFmpegResolver()

    if force and resolver.local_path.exists():
        resolver.local_path.unlink()
        console.print("[yellow]Removed existing FFmpeg binary.[/yellow]")

    try:
        path = resolve_ffmpeg(auto_download=True, **ffmpeg_prompt_callbacks())
        log_success(f"FFmpeg ready at: {path}")
    except Exception as e:
        log_error(str(e))
        raise typer.Exit(1) from None
