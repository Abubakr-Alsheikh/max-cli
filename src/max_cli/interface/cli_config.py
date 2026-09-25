import typer

from max_cli.interface.config import grab_app, manage_app, setup_app

app = typer.Typer(help="Manage API keys and settings.")

# Mount the sub-apps without a name so their commands sit directly under
# `max config` (`max config show`). A name made each one a nested group, so
# only `max config show show` worked.
app.add_typer(setup_app)
app.add_typer(grab_app)
app.add_typer(manage_app)


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
