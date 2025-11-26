class MaxError(Exception):
    """Base class for expected errors in the CLI."""

    pass


class ResourceNotFoundError(MaxError):
    """Raised when a file or folder is missing."""

    pass


class ValidationError(MaxError):
    """Raised when input arguments are invalid."""

    pass
