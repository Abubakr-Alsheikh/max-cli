"""Whether a command that changes files may go ahead without asking."""


def skip_confirmation(force: bool) -> bool:
    """True for `--force`, or when CONFIRM_DESTRUCTIVE is off.

    `files shred` doesn't use this: it can't be undone, so it asks unless
    `--force` is given.
    """
    from max_cli.config import settings

    return force or not settings.CONFIRM_DESTRUCTIVE
