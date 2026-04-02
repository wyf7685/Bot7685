class CosClientError(RuntimeError):
    """Base exception raised by COS client operations."""


class CosHttpStatusError(CosClientError):
    """Raised when COS returns a 4xx/5xx response."""

    def __init__(
        self,
        method: str,
        url: str,
        status_code: int,
        body: str,
    ) -> None:
        self.method = method
        self.url = url
        self.status_code = status_code
        self.body = body
        super().__init__(f"COS request failed: {method} {url} -> {status_code}: {body}")


class CosResponseParseError(CosClientError):
    """Raised when COS response cannot be parsed as expected."""
