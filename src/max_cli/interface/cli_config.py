import typer

from max_cli.interface.config import setup_app, grab_app, manage_app

app = typer.Typer(help="Manage API keys and settings.")

app.add_typer(setup_app, name="setup")
app.add_typer(grab_app, name="grab")
app.add_typer(manage_app, name="show")
app.add_typer(manage_app, name="save")
app.add_typer(manage_app, name="reset")
app.add_typer(manage_app, name="validate")
app.add_typer(manage_app, name="export")
app.add_typer(manage_app, name="import")


@app.command("setup-ffmpeg")
def setup_ffmpeg(
    force: bool = typer.Option(False, "--force", "-f", help="Force re-download"),
):
    """Download and install FFmpeg binary to ~/.max_cli/bin/."""
    from max_cli.common.ffmpeg_resolver import FFmpegResolver, resolve_ffmpeg
    from max_cli.common.logger import console, log_error, log_success

    resolver = FFmpegResolver()

    if force and resolver.local_path.exists():
        resolver.local_path.unlink()
        console.print("[yellow]Removed existing FFmpeg binary.[/yellow]")

    try:
        path = resolve_ffmpeg(auto_download=True)
        log_success(f"FFmpeg ready at: {path}")
    except Exception as e:
        log_error(str(e))
        raise typer.Exit(1)
