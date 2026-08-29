import re
from urllib.parse import urlsplit

_PARTICIPANT_ALIAS_PATTERN = r"p_[0-9a-f]{16}"
_PARTICIPANT_ALIAS_RE = re.compile(rf"^{_PARTICIPANT_ALIAS_PATTERN}$")
_CITATION_ID_RE = re.compile(r"^s[1-9][0-9]*$")
_IMAGE_LABEL_RE = re.compile(r"^image-[1-9][0-9]*$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_MESSAGE_IMAGE_ID_PATTERN = r"i[1-9][0-9]*"
_MESSAGE_IMAGE_ID_RE = re.compile(rf"^{_MESSAGE_IMAGE_ID_PATTERN}$")


def _nonempty(value: str, field_name: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError(f"{field_name} must not be empty")
    return value


def _participant_alias(value: str) -> str:
    if not _PARTICIPANT_ALIAS_RE.fullmatch(value):
        raise ValueError("participant alias must match p_<16 lowercase hex characters>")
    return value


def _citation_id(value: str) -> str:
    if not _CITATION_ID_RE.fullmatch(value):
        raise ValueError("citation_id must match s<positive integer>")
    return value


def _image_label(value: str) -> str:
    if not _IMAGE_LABEL_RE.fullmatch(value):
        raise ValueError("image label must match image-<positive integer>")
    return value


def _message_image_id(value: str) -> str:
    if not _MESSAGE_IMAGE_ID_RE.fullmatch(value):
        raise ValueError("message image ID must match i<positive integer>")
    return value


def _sha256(value: str) -> str:
    value = value.lower()
    if not _SHA256_RE.fullmatch(value):
        raise ValueError("sha256 must contain 64 hexadecimal characters")
    return value


def _http_url(value: str, field_name: str) -> str:
    value = _nonempty(value, field_name)
    if any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise ValueError(f"{field_name} must not contain control characters")
    try:
        parsed = urlsplit(value)
        _ = parsed.port
    except ValueError as error:
        raise ValueError(f"{field_name} is not a valid HTTP URL") from error
    if parsed.scheme.lower() not in {"http", "https"} or parsed.hostname is None:
        raise ValueError(f"{field_name} must be an absolute HTTP(S) URL")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError(f"{field_name} must not contain user information")
    return value
