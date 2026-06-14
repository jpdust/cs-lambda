class ExternalApiException(Exception):
    """Raised when the upstream currency API returns an HTTP error (4xx/5xx)."""

    def __init__(self, message: str, status_code: int) -> None:
        super().__init__(message)
        self.status_code = status_code


class NetworkException(Exception):
    """Raised when the upstream currency API is unreachable (connection/timeout errors)."""
