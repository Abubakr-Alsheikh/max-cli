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
