class S3ServiceError(RuntimeError):
    """Base exception for process-level S3 service failures."""


class S3ConfigurationError(S3ServiceError):
    def __init__(self, *, cause: BaseException | None = None) -> None:
        self.cause = cause
        super().__init__("S3 service is not configured")


class S3ConfigurationConflictError(S3ConfigurationError):
    """Raised when an administrator writes against a stale revision."""


class S3ConfigurationInUseError(S3ConfigurationError):
    """Raised when changing a namespace would orphan temporary objects."""


__all__ = [
    "S3ConfigurationConflictError",
    "S3ConfigurationError",
    "S3ConfigurationInUseError",
    "S3ServiceError",
]
