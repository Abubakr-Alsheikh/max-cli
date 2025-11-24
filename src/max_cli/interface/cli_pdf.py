import typer
from max_cli.common.logger import console, log_error

app = typer.Typer()


@app.command("optimize")
def optimize_pdf():
    """
    Optimizes PDF files (placeholder).
    """
    console.print("[info]PDF optimization not yet implemented.[/info]")
    log_error("This feature is under development.")


@app.command("merge")
def merge_pdfs():
    """
    Merges multiple PDF files into one (placeholder).
    """
    console.print("[info]PDF merging not yet implemented.[/info]")
    log_error("This feature is under development.")
