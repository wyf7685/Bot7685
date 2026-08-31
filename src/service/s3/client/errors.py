class S3ClientError(RuntimeError):
    """Base exception raised by S3 client operations."""


class S3HttpStatusError(S3ClientError):
    """Raised when an S3 endpoint returns an unsuccessful HTTP status."""

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
        super().__init__(f"S3 request failed: {method} {url} -> {status_code}: {body}")


class S3ResponseParseError(S3ClientError):
    """Raised when a successful S3 response violates the expected protocol."""


__all__ = ["S3ClientError", "S3HttpStatusError", "S3ResponseParseError"]
