class MaxError(Exception):
    """Base class for expected errors in the CLI."""

    pass


class ResourceNotFoundError(MaxError):
    """Raised when a file or folder is missing."""

    pass


class ValidationError(MaxError):
    """Raised when input arguments are invalid."""

    pass


class ConfigurationError(MaxError):
    """Raised when configuration is invalid or missing."""

    pass


class ProcessingError(MaxError):
    """Raised when file processing fails."""

    pass


class NetworkError(MaxError):
    """Raised when network operations fail."""

    pass


class AIError(MaxError):
    """Raised when AI operations fail."""

    pass
