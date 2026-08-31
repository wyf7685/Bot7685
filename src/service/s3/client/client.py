import contextlib
import xml.etree.ElementTree as ET
from collections.abc import AsyncGenerator, AsyncIterator, Iterable, Mapping
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from types import TracebackType
from typing import Literal, Self
from urllib.parse import quote

import anyio
import anyio.lowlevel
import httpx

from ..config import S3Config
from .auth import (
    _UNSIGNED_PAYLOAD,
    AWSSigV4Signer,
    _encode_query_kv,
    _format_query_kv,
)
from .errors import S3ClientError, S3HttpStatusError, S3ResponseParseError
from .models import (
    CompletedPart,
    HeadObjectOutput,
    ListObjectsCommonPrefix,
    ListObjectsContents,
)


def _parse_xml(content: bytes) -> ET.Element:
    try:
        return ET.fromstring(content)  # noqa: S314
    except ET.ParseError as error:
        raise S3ResponseParseError("Failed to parse S3 XML response") from error


def _find_required_text(root: ET.Element, tag: str) -> str:
    value = root.findtext(f".//{{*}}{tag}")
    if value is None or value == "":
        raise S3ResponseParseError(f"Missing field in S3 response: {tag}")
    return value


def _build_complete_multipart_xml(parts: Iterable[CompletedPart]) -> bytes:
    root = ET.Element("CompleteMultipartUpload")
    for part in parts:
        node = ET.SubElement(root, "Part")
        ET.SubElement(node, "PartNumber").text = str(part["PartNumber"])
        ET.SubElement(node, "ETag").text = part["ETag"]
    return ET.tostring(root, encoding="utf-8")


class AsyncS3Client:
    """Small async SigV4 client for AWS S3-compatible object stores."""

    def __init__(self, config: S3Config) -> None:
        self._config = config
        self._request_host = self._compute_host(config.endpoint_url)
        presign_endpoint = config.presign_endpoint_url or config.endpoint_url
        self._presign_host = self._compute_host(presign_endpoint)
        self._base_url = f"{config.scheme}://{self._request_host}"
        self._presign_base_url = f"{config.scheme}://{self._presign_host}"
        self._client: httpx.AsyncClient | None = None
        self._signer = AWSSigV4Signer(
            access_key_id=config.access_key_id.get_secret_value(),
            secret_access_key=config.secret_access_key.get_secret_value(),
            region=config.region,
        )
        self._semaphore = anyio.Semaphore(config.max_concurrency)

    def _compute_host(self, endpoint_url: str | None) -> str:
        if endpoint_url is None:
            return f"{self._config.bucket}.s3.{self._config.region}.amazonaws.com"
        if self._config.path_style:
            return endpoint_url
        return f"{self._config.bucket}.{endpoint_url}"

    async def __aenter__(self) -> Self:
        if self._client is None:
            transport = httpx.AsyncHTTPTransport(retries=3, http2=True)
            self._client = httpx.AsyncClient(
                base_url=self._base_url,
                timeout=float(self._config.timeout_seconds),
                transport=transport,
            )
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None = None,
        exc_value: BaseException | None = None,
        traceback: TracebackType | None = None,
    ) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    def _require_client(self) -> httpx.AsyncClient:
        if self._client is None:
            raise S3ClientError("AsyncS3Client must be used with 'async with'")
        return self._client

    @staticmethod
    def _normalize_key(key: str) -> str:
        return key.removeprefix("/")

    def _build_request_path(self, key: str) -> str:
        normalized = self._normalize_key(key)
        encoded = quote(normalized, safe="/-_.~").replace("./", ".%2F")
        path = f"/{encoded}" if encoded else "/"
        if not self._config.path_style:
            return path
        if path == "/":
            return f"/{self._config.bucket}"
        return f"/{self._config.bucket}{path}"

    @staticmethod
    def _normalize_params(
        params: Mapping[str, str | int] | None,
    ) -> dict[str, str]:
        if params is None:
            return {}
        return {str(key): str(value) for key, value in params.items()}

    def _build_signed_headers(
        self,
        *,
        method: str,
        canonical_uri: str,
        params: Mapping[str, str],
        headers: Mapping[str, str] | None,
        now: datetime,
    ) -> dict[str, str]:
        signed: dict[str, str] = {
            "host": self._request_host,
            "x-amz-date": now.strftime("%Y%m%dT%H%M%SZ"),
            "x-amz-content-sha256": _UNSIGNED_PAYLOAD,
        }
        if self._config.session_token is not None:
            signed["x-amz-security-token"] = (
                self._config.session_token.get_secret_value()
            )
        if headers:
            signed.update(headers)
        signed["Authorization"] = self._signer.build_authorization(
            method=method,
            canonical_uri=canonical_uri,
            params=params,
            headers=signed,
            payload_hash=_UNSIGNED_PAYLOAD,
            now=now,
        )
        return signed

    async def _request(
        self,
        *,
        method: Literal["GET", "POST", "PUT", "DELETE", "HEAD"],
        key: str,
        params: Mapping[str, str | int] | None = None,
        headers: Mapping[str, str] | None = None,
        content: bytes | None = None,
    ) -> httpx.Response:
        query = self._normalize_params(params)
        request_path = self._build_request_path(key)
        canonical_query = _format_query_kv(_encode_query_kv(query))
        now = datetime.now(UTC)
        signed_headers = self._build_signed_headers(
            method=method,
            canonical_uri=request_path,
            params=query,
            headers=headers,
            now=now,
        )
        url = f"{request_path}?{canonical_query}" if canonical_query else request_path

        async with self._semaphore:
            response = await self._require_client().request(
                method=method,
                url=url,
                headers=signed_headers,
                content=content,
            )
        if response.status_code >= 400:
            body = response.text.strip() or "<empty body>"
            raise S3HttpStatusError(
                method=method,
                url=str(response.request.url),
                status_code=response.status_code,
                body=body,
            )
        return response

    async def head_bucket(self) -> bool:
        try:
            await self._request(method="HEAD", key="")
        except S3HttpStatusError as error:
            if error.status_code == 404:
                return False
            raise
        return True

    async def list_objects(
        self,
        *,
        prefix: str | None = None,
        delimiter: str | None = "/",
        max_keys: int = 1000,
    ) -> AsyncGenerator[ListObjectsContents | ListObjectsCommonPrefix]:
        params: dict[str, str | int] = {
            "list-type": "2",
            "max-keys": max_keys,
        }
        if prefix is not None:
            params["prefix"] = prefix
        if delimiter is not None:
            params["delimiter"] = delimiter

        seen_tokens: set[str] = set()
        while True:
            response = await self._request(method="GET", key="", params=params)
            root = _parse_xml(response.content)
            for node in root.findall(".//{*}CommonPrefixes"):
                yield ListObjectsCommonPrefix(
                    prefix=_find_required_text(node, "Prefix")
                )
                await anyio.lowlevel.checkpoint()
            for node in root.findall(".//{*}Contents"):
                try:
                    size = int(_find_required_text(node, "Size"))
                    modified = datetime.fromisoformat(
                        _find_required_text(node, "LastModified")
                    )
                except ValueError as error:
                    raise S3ResponseParseError(
                        "Invalid object metadata in list response"
                    ) from error
                yield ListObjectsContents(
                    key=_find_required_text(node, "Key"),
                    size=size,
                    etag=_find_required_text(node, "ETag"),
                    last_modified=modified,
                )
                await anyio.lowlevel.checkpoint()

            truncated = _find_required_text(root, "IsTruncated").lower()
            if truncated != "true":
                return
            token = _find_required_text(root, "NextContinuationToken")
            if token in seen_tokens:
                raise S3ResponseParseError(
                    "S3 list response repeated its continuation token"
                )
            seen_tokens.add(token)
            params["continuation-token"] = token

    async def head_object(self, key: str) -> HeadObjectOutput | None:
        try:
            response = await self._request(method="HEAD", key=key)
        except S3HttpStatusError as error:
            if error.status_code == 404:
                return None
            raise

        length = response.headers.get("Content-Length")
        etag = response.headers.get("ETag")
        modified = response.headers.get("Last-Modified")
        if not length:
            raise S3ResponseParseError("Missing Content-Length in HEAD response")
        if not etag:
            raise S3ResponseParseError("Missing ETag in HEAD response")
        if not modified:
            raise S3ResponseParseError("Missing Last-Modified in HEAD response")
        try:
            content_length = int(length)
            last_modified = parsedate_to_datetime(modified)
        except (TypeError, ValueError) as error:
            raise S3ResponseParseError("Invalid metadata in HEAD response") from error
        if last_modified.tzinfo is None:
            last_modified = last_modified.replace(tzinfo=UTC)
        else:
            last_modified = last_modified.astimezone(UTC)
        return HeadObjectOutput(content_length, etag, last_modified)

    async def get_object(
        self,
        key: str,
        byte_range: tuple[int, int] | None = None,
    ) -> bytes:
        headers: dict[str, str] = {}
        if byte_range is not None:
            headers["Range"] = f"bytes={byte_range[0]}-{byte_range[1]}"
        response = await self._request(method="GET", key=key, headers=headers)
        return response.content

    async def put_object(
        self,
        key: str,
        data: bytes,
        *,
        headers: Mapping[str, str] | None = None,
    ) -> str:
        response = await self._request(
            method="PUT",
            key=key,
            content=data,
            headers=headers,
        )
        etag = response.headers.get("ETag")
        if not etag:
            raise S3ResponseParseError("Missing ETag in PUT response")
        return etag

    @contextlib.asynccontextmanager
    async def stream_get(
        self,
        key: str,
        *,
        range_start: int | None = None,
    ) -> AsyncIterator[httpx.Response]:
        headers: dict[str, str] = {}
        if range_start is not None and range_start > 0:
            headers["Range"] = f"bytes={range_start}-"
        request_path = self._build_request_path(key)
        now = datetime.now(UTC)
        signed_headers = self._build_signed_headers(
            method="GET",
            canonical_uri=request_path,
            params={},
            headers=headers,
            now=now,
        )

        async with self._semaphore:
            request = self._require_client().build_request(
                method="GET",
                url=request_path,
                headers=signed_headers,
            )
            response = await self._require_client().send(request, stream=True)
            try:
                if response.status_code >= 400:
                    body_bytes = await self._read_limited_body(response, limit=4096)
                    body = body_bytes.decode(errors="replace").strip()
                    raise S3HttpStatusError(
                        method="GET",
                        url=str(response.request.url),
                        status_code=response.status_code,
                        body=body or "<empty body>",
                    )
                yield response
            finally:
                with anyio.CancelScope(shield=True):
                    await response.aclose()

    @staticmethod
    async def _read_limited_body(
        response: httpx.Response,
        *,
        limit: int,
    ) -> bytes:
        if limit <= 0:
            return b"<body omitted>"
        length = response.headers.get("Content-Length")
        if length is None:
            return b"<body omitted: unknown content length>"
        try:
            declared = int(length)
        except ValueError:
            return b"<body omitted: invalid content length>"
        if declared < 0 or declared > limit:
            return b"<body omitted: content length exceeds diagnostic limit>"
        return (await response.aread())[:limit]

    async def delete_object(self, key: str) -> None:
        await self._request(method="DELETE", key=key)

    async def create_multipart_upload(self, key: str) -> str:
        response = await self._request(
            method="POST",
            key=key,
            params={"uploads": ""},
        )
        return _find_required_text(_parse_xml(response.content), "UploadId")

    async def upload_part(
        self,
        key: str,
        data: bytes,
        part_number: int,
        upload_id: str,
    ) -> str:
        response = await self._request(
            method="PUT",
            key=key,
            params={"partNumber": part_number, "uploadId": upload_id},
            content=data,
        )
        etag = response.headers.get("ETag")
        if not etag:
            raise S3ResponseParseError("Missing ETag in upload-part response")
        return etag

    async def complete_multipart_upload(
        self,
        key: str,
        upload_id: str,
        parts: list[CompletedPart],
    ) -> None:
        response = await self._request(
            method="POST",
            key=key,
            params={"uploadId": upload_id},
            headers={"Content-Type": "application/xml"},
            content=_build_complete_multipart_xml(parts),
        )
        _find_required_text(_parse_xml(response.content), "ETag")

    async def abort_multipart_upload(self, key: str, upload_id: str) -> None:
        await self._request(
            method="DELETE",
            key=key,
            params={"uploadId": upload_id},
        )

    def presign_url(
        self,
        key: str,
        *,
        method: Literal["GET", "PUT", "DELETE", "HEAD"] = "GET",
        expires_in: int,
    ) -> str:
        request_path = self._build_request_path(key)
        token = (
            self._config.session_token.get_secret_value()
            if self._config.session_token is not None
            else None
        )
        query = self._signer.build_presigned_query(
            method=method,
            canonical_uri=request_path,
            host=self._presign_host,
            expires_in=expires_in,
            now=datetime.now(UTC),
            session_token=token,
        )
        encoded = _format_query_kv(_encode_query_kv(query))
        return f"{self._presign_base_url}{request_path}?{encoded}"


__all__ = ["AsyncS3Client"]
