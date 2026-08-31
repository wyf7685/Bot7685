"""Stable public contracts for Bot7685 S3 consumers."""

from . import cleanup as _cleanup
from .client import (
    HeadObjectOutput,
    S3ClientError,
    S3HttpStatusError,
    S3ResponseParseError,
)
from .config import S3Config
from .exceptions import (
    S3ConfigurationConflictError,
    S3ConfigurationError,
    S3ConfigurationInUseError,
    S3ServiceError,
)
from .service import S3ConfigurationSnapshot, S3Service, get_s3_service
from .transfer import UploadSource

_HANDLER_MODULES = (_cleanup,)

__all__ = [
    "HeadObjectOutput",
    "S3ClientError",
    "S3Config",
    "S3ConfigurationConflictError",
    "S3ConfigurationError",
    "S3ConfigurationInUseError",
    "S3ConfigurationSnapshot",
    "S3HttpStatusError",
    "S3ResponseParseError",
    "S3Service",
    "S3ServiceError",
    "UploadSource",
    "get_s3_service",
]
