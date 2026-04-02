import hashlib
import hmac
import time
from collections.abc import Mapping
from urllib.parse import quote

_SAFE_CHARS = "-_.~"
_VALID_HEADERS = frozenset(
    {
        "cache-control",
        "content-disposition",
        "content-encoding",
        "content-type",
        "content-md5",
        "content-length",
        "expect",
        "expires",
        "host",
        "if-match",
        "if-modified-since",
        "if-none-match",
        "if-unmodified-since",
        "origin",
        "range",
        "transfer-encoding",
        "pic-operations",
    }
)


def _ensure_sign_path(path: str) -> str:
    if not path:
        return "/"
    if path.startswith("/"):
        return path
    return f"/{path}"


def _encode_kv(data: Mapping[str, str]) -> list[tuple[str, str]]:
    encoded: list[tuple[str, str]] = []
    for key, value in data.items():
        encoded_key = quote(str(key), safe=_SAFE_CHARS).lower()
        encoded_value = quote(str(value), safe=_SAFE_CHARS)
        encoded.append((encoded_key, encoded_value))
    encoded.sort(key=lambda item: item[0])
    return encoded


def _format_kv(encoded: list[tuple[str, str]]) -> str:
    return "&".join(f"{key}={value}" for key, value in encoded)


def filter_sign_headers(headers: Mapping[str, str]) -> dict[str, str]:
    valid_headers: dict[str, str] = {}
    for key, value in headers.items():
        lower = key.lower()
        if lower in _VALID_HEADERS or lower.startswith(("x-cos-", "x-ci-")):
            valid_headers[key] = value
    return valid_headers


class CosV5Signer:
    def __init__(self, secret_id: str, secret_key: str) -> None:
        self._secret_id = secret_id
        self._secret_key = secret_key

    def build_authorization(
        self,
        *,
        method: str,
        path: str,
        params: Mapping[str, str],
        headers: Mapping[str, str],
        expired: int,
        host: str | None = None,
        now: int | None = None,
    ) -> str:
        if expired <= 0:
            raise ValueError("expired must be greater than 0")

        sign_path = _ensure_sign_path(path)
        sign_headers = dict(headers)
        if host is not None and not any(key.lower() == "host" for key in sign_headers):
            sign_headers["host"] = host
        sign_headers = filter_sign_headers(sign_headers)

        encoded_params = _encode_kv(params)
        encoded_headers = _encode_kv(sign_headers)

        format_str = (
            f"{method.lower()}\n"
            f"{sign_path}\n"
            f"{_format_kv(encoded_params)}\n"
            f"{_format_kv(encoded_headers)}\n"
        )

        start_time = int(time.time() if now is None else now)
        sign_time = f"{start_time - 60};{start_time + expired}"

        sha1_hex = hashlib.sha1(format_str.encode()).hexdigest()  # noqa: S324
        string_to_sign = f"sha1\n{sign_time}\n{sha1_hex}\n"

        sign_key = hmac.new(
            self._secret_key.encode(),
            sign_time.encode(),
            digestmod=hashlib.sha1,
        ).hexdigest()
        signature = hmac.new(
            sign_key.encode(),
            string_to_sign.encode(),
            digestmod=hashlib.sha1,
        ).hexdigest()

        header_list = ";".join(key for key, _ in encoded_headers)
        param_list = ";".join(key for key, _ in encoded_params)

        return (
            "q-sign-algorithm=sha1"
            f"&q-ak={self._secret_id}"
            f"&q-sign-time={sign_time}"
            f"&q-key-time={sign_time}"
            f"&q-header-list={header_list}"
            f"&q-url-param-list={param_list}"
            f"&q-signature={signature}"
        )
