"""Remember whether a command reported an error, so `max` can exit 1.

Commands report failures with `log_error` and often return normally, which
used to leave the exit code at 0. `log_error` calls `mark_error()`, and
`max_cli.main.main()` turns a clean exit into exit code 1 when an error was
reported. Scripts can then detect failures. Stdlib only, so importing it
costs nothing at startup.
"""

_error_reported = False


def mark_error() -> None:
    global _error_reported
    _error_reported = True


def error_reported() -> bool:
    return _error_reported


def reset() -> None:
    global _error_reported
    _error_reported = False
