# Config command modules
from max_cli.interface.config.setup import app as setup_app
from max_cli.interface.config.grab import app as grab_app
from max_cli.interface.config.manage import app as manage_app

__all__ = ["setup_app", "grab_app", "manage_app"]
