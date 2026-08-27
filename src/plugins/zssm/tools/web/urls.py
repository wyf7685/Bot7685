import ipaddress
import re
from typing import Literal, cast
from urllib.parse import SplitResult, urlsplit, urlunsplit

from .sources.contracts import ValidatedTarget

_DEFAULT_PORTS = {"http": 80, "https": 443}
_MAX_URL_CHARS = 4096
_HOST_LABEL_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")


class InvalidWebUrlError(ValueError):
    """The URL is outside the accepted public HTTP(S) syntax policy."""


def normalize_http_url(url: str) -> str:
    return validate_target(url).url


def validate_target(url: str) -> ValidatedTarget:
    if not isinstance(url, str):
        raise InvalidWebUrlError
    url = url.strip()
    if (
        not url
        or len(url) > _MAX_URL_CHARS
        or any(ord(character) < 32 for character in url)
    ):
        raise InvalidWebUrlError
    try:
        parsed = urlsplit(url)
    except ValueError:
        raise InvalidWebUrlError from None
    scheme = parsed.scheme.casefold()
    if scheme not in _DEFAULT_PORTS or not parsed.netloc or "\\" in parsed.netloc:
        raise InvalidWebUrlError
    if parsed.username is not None or parsed.password is not None:
        raise InvalidWebUrlError
    hostname = parsed.hostname
    if hostname is None:
        raise InvalidWebUrlError
    hostname = hostname.rstrip(".")
    if not hostname:
        raise InvalidWebUrlError
    try:
        ipaddress.ip_address(hostname)
    except ValueError:
        pass
    else:
        raise InvalidWebUrlError
    try:
        ascii_hostname = hostname.encode("idna").decode("ascii").casefold()
        port = parsed.port or _DEFAULT_PORTS[scheme]
    except UnicodeError, ValueError:
        raise InvalidWebUrlError from None
    if len(ascii_hostname) > 253 or any(
        not _HOST_LABEL_RE.fullmatch(label) for label in ascii_hostname.split(".")
    ):
        raise InvalidWebUrlError
    if port != _DEFAULT_PORTS[scheme]:
        raise InvalidWebUrlError

    path = parsed.path or "/"
    canonical = SplitResult(scheme, ascii_hostname, path, parsed.query, "")
    normalized_url = urlunsplit(canonical)
    origin = f"{scheme}://{ascii_hostname}"
    return ValidatedTarget(
        url=normalized_url,
        scheme=cast("Literal['http', 'https']", scheme),
        hostname=ascii_hostname,
        port=port,
        origin=origin,
        host_header=ascii_hostname,
    )


__all__ = ["InvalidWebUrlError", "normalize_http_url", "validate_target"]
