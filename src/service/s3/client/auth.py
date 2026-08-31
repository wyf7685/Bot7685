import hashlib
import hmac
from collections.abc import Mapping
from datetime import datetime
from urllib.parse import quote

_SAFE_CHARS = "-_.~"
_UNSIGNED_PAYLOAD = "UNSIGNED-PAYLOAD"


def _uri_encode(value: str) -> str:
    return quote(str(value), safe=_SAFE_CHARS)


def _encode_query_kv(data: Mapping[str, str]) -> list[tuple[str, str]]:
    encoded = [(_uri_encode(key), _uri_encode(value)) for key, value in data.items()]
    encoded.sort(key=lambda item: (item[0], item[1]))
    return encoded


def _format_query_kv(encoded: list[tuple[str, str]]) -> str:
    return "&".join(f"{key}={value}" for key, value in encoded)


def _canonical_headers(headers: Mapping[str, str]) -> tuple[str, str]:
    normalized = [
        (key.lower(), " ".join(value.strip().split())) for key, value in headers.items()
    ]
    normalized.sort(key=lambda item: item[0])
    canonical = "".join(f"{key}:{value}\n" for key, value in normalized)
    signed = ";".join(key for key, _ in normalized)
    return canonical, signed


class AWSSigV4Signer:
    _SERVICE = "s3"
    _ALGORITHM = "AWS4-HMAC-SHA256"

    def __init__(
        self,
        access_key_id: str,
        secret_access_key: str,
        region: str,
    ) -> None:
        self._access_key_id = access_key_id
        self._secret_access_key = secret_access_key
        self._region = region

    @staticmethod
    def _hmac_sha256(key: bytes, message: str) -> bytes:
        return hmac.new(key, message.encode(), hashlib.sha256).digest()

    @staticmethod
    def _sha256_hex(data: str) -> str:
        return hashlib.sha256(data.encode()).hexdigest()

    def _credential_scope(self, now: datetime) -> str:
        return f"{now:%Y%m%d}/{self._region}/{self._SERVICE}/aws4_request"

    def _derive_signing_key(self, date_stamp: str) -> bytes:
        key = ("AWS4" + self._secret_access_key).encode()
        key = self._hmac_sha256(key, date_stamp)
        key = self._hmac_sha256(key, self._region)
        key = self._hmac_sha256(key, self._SERVICE)
        return self._hmac_sha256(key, "aws4_request")

    def _signature(
        self,
        *,
        method: str,
        canonical_uri: str,
        params: Mapping[str, str],
        headers: Mapping[str, str],
        payload_hash: str,
        now: datetime,
    ) -> tuple[str, str]:
        canonical_query = _format_query_kv(_encode_query_kv(params))
        canonical_headers, signed_headers = _canonical_headers(headers)
        canonical_request = (
            f"{method.upper()}\n{canonical_uri}\n{canonical_query}\n"
            f"{canonical_headers}\n{signed_headers}\n{payload_hash}"
        )
        scope = self._credential_scope(now)
        string_to_sign = (
            f"{self._ALGORITHM}\n{now:%Y%m%dT%H%M%SZ}\n{scope}\n"
            f"{self._sha256_hex(canonical_request)}"
        )
        signing_key = self._derive_signing_key(f"{now:%Y%m%d}")
        signature = hmac.new(
            signing_key,
            string_to_sign.encode(),
            hashlib.sha256,
        ).hexdigest()
        return signed_headers, signature

    def build_authorization(
        self,
        *,
        method: str,
        canonical_uri: str,
        params: Mapping[str, str],
        headers: Mapping[str, str],
        payload_hash: str,
        now: datetime,
    ) -> str:
        signed_headers, signature = self._signature(
            method=method,
            canonical_uri=canonical_uri,
            params=params,
            headers=headers,
            payload_hash=payload_hash,
            now=now,
        )
        scope = self._credential_scope(now)
        return (
            f"{self._ALGORITHM} "
            f"Credential={self._access_key_id}/{scope}, "
            f"SignedHeaders={signed_headers}, Signature={signature}"
        )

    def build_presigned_query(
        self,
        *,
        method: str,
        canonical_uri: str,
        host: str,
        expires_in: int,
        now: datetime,
        session_token: str | None = None,
    ) -> dict[str, str]:
        if not 1 <= expires_in <= 604800:
            raise ValueError("expires_in must be between 1 and 604800 seconds")

        scope = self._credential_scope(now)
        query = {
            "X-Amz-Algorithm": self._ALGORITHM,
            "X-Amz-Credential": f"{self._access_key_id}/{scope}",
            "X-Amz-Date": f"{now:%Y%m%dT%H%M%SZ}",
            "X-Amz-Expires": str(expires_in),
            "X-Amz-SignedHeaders": "host",
        }
        if session_token is not None:
            query["X-Amz-Security-Token"] = session_token

        _, signature = self._signature(
            method=method,
            canonical_uri=canonical_uri,
            params=query,
            headers={"host": host},
            payload_hash=_UNSIGNED_PAYLOAD,
            now=now,
        )
        query["X-Amz-Signature"] = signature
        return query


__all__ = [
    "_UNSIGNED_PAYLOAD",
    "AWSSigV4Signer",
    "_encode_query_kv",
    "_format_query_kv",
]
