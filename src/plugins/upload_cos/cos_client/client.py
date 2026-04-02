import xml.etree.ElementTree as ET
from collections.abc import Mapping, Sequence
from types import TracebackType
from typing import Self
from urllib.parse import quote, urlencode

import httpx

from .auth import CosV5Signer
from .errors import CosClientError, CosHttpStatusError, CosResponseParseError
from .models import MultipartUploadPart


def _parse_xml(content: bytes) -> ET.Element:
    try:
        return ET.fromstring(content)  # noqa: S314
    except ET.ParseError as err:
        raise CosResponseParseError("Failed to parse COS XML response") from err


def _find_required_text(root: ET.Element, tag: str) -> str:
    value = root.findtext(f".//{tag}")
    if value is None or value == "":
        raise CosResponseParseError(f"Missing field in COS response: {tag}")
    return value


def _build_complete_multipart_xml(parts: Sequence[MultipartUploadPart]) -> bytes:
    root = ET.Element("CompleteMultipartUpload")
    for part in parts:
        node = ET.SubElement(root, "Part")
        ET.SubElement(node, "PartNumber").text = str(part["PartNumber"])
        ET.SubElement(node, "ETag").text = part["ETag"]
    return ET.tostring(root, encoding="utf-8")


class AsyncCosClient:
    def __init__(
        self,
        *,
        region: str,
        bucket: str,
        secret_id: str,
        secret_key: str,
        token: str | None = None,
        scheme: str = "https",
        timeout: float = 30,
    ) -> None:
        self._host = f"{bucket}.cos.{region}.myqcloud.com"
        self._base_url = f"{scheme}://{self._host}"
        self._token = token
        self._timeout = timeout
        self._client: httpx.AsyncClient | None = None
        self._signer = CosV5Signer(secret_id=secret_id, secret_key=secret_key)

    async def __aenter__(self) -> Self:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self._base_url,
                timeout=self._timeout,
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
            raise CosClientError("AsyncCosClient must be used with 'async with'")
        return self._client

    @staticmethod
    def _normalize_key(key: str) -> str:
        return key.removeprefix("/")

    def _build_sign_path(self, key: str) -> str:
        normalized = self._normalize_key(key)
        return f"/{normalized}" if normalized else "/"

    def _build_request_path(self, key: str) -> str:
        normalized = self._normalize_key(key)
        encoded = quote(normalized, safe="/-_.~")
        encoded = encoded.replace("./", ".%2F")
        return f"/{encoded}" if encoded else "/"

    @staticmethod
    def _normalize_params(params: Mapping[str, str | int] | None) -> dict[str, str]:
        if params is None:
            return {}
        return {str(key): str(value) for key, value in params.items()}

    @staticmethod
    def _normalize_headers(headers: Mapping[str, str] | None) -> dict[str, str]:
        if headers is None:
            return {}
        return {str(key): str(value) for key, value in headers.items()}

    @staticmethod
    def _has_header(headers: Mapping[str, str], name: str) -> bool:
        lower = name.lower()
        return any(key.lower() == lower for key in headers)

    def _build_signed_headers(
        self,
        *,
        method: str,
        sign_path: str,
        params: Mapping[str, str],
        headers: Mapping[str, str] | None,
        expired: int,
    ) -> dict[str, str]:
        sign_headers = self._normalize_headers(headers)
        if not self._has_header(sign_headers, "Host"):
            sign_headers["Host"] = self._host
        if self._token and not self._has_header(sign_headers, "x-cos-security-token"):
            sign_headers["x-cos-security-token"] = self._token

        authorization = self._signer.build_authorization(
            method=method,
            path=sign_path,
            params=params,
            headers=sign_headers,
            expired=expired,
            host=self._host,
        )
        sign_headers["Authorization"] = authorization
        return sign_headers

    async def _request(
        self,
        *,
        method: str,
        key: str,
        params: Mapping[str, str | int] | None = None,
        headers: Mapping[str, str] | None = None,
        content: bytes | None = None,
        expired: int = 300,
    ) -> httpx.Response:
        query = self._normalize_params(params)
        sign_path = self._build_sign_path(key)
        request_path = self._build_request_path(key)
        signed_headers = self._build_signed_headers(
            method=method,
            sign_path=sign_path,
            params=query,
            headers=headers,
            expired=expired,
        )

        response = await self._require_client().request(
            method=method,
            url=request_path,
            params=query,
            headers=signed_headers,
            content=content,
        )

        if response.status_code >= 400:
            body = response.text.strip() or "<empty body>"
            raise CosHttpStatusError(
                method=method,
                url=str(response.request.url),
                status_code=response.status_code,
                body=body,
            )

        return response

    async def put_object(self, key: str, data: bytes) -> None:
        await self._request(method="PUT", key=key, content=data)

    async def delete_object(self, key: str) -> None:
        await self._request(method="DELETE", key=key)

    async def get_presigned_url(self, key: str, method: str, expired: int) -> str:
        query: dict[str, str] = {}
        headers = self._build_signed_headers(
            method=method,
            sign_path=self._build_sign_path(key),
            params=query,
            headers=None,
            expired=expired,
        )
        authorization = headers["Authorization"]
        sign_query = urlencode(
            dict(item.split("=", 1) for item in authorization.split("&"))
        )
        return f"{self._base_url}{self._build_request_path(key)}?{sign_query}"

    async def create_multipart_upload(self, key: str) -> str:
        response = await self._request(
            method="POST",
            key=key,
            params={"uploads": ""},
        )
        root = _parse_xml(response.content)
        return _find_required_text(root, "UploadId")

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
        if etag is None or etag == "":
            raise CosResponseParseError("Missing ETag in upload_part response")
        return etag

    async def complete_multipart_upload(
        self,
        key: str,
        upload_id: str,
        parts: list[MultipartUploadPart],
    ) -> None:
        response = await self._request(
            method="POST",
            key=key,
            params={"uploadId": upload_id},
            headers={"Content-Type": "application/xml"},
            content=_build_complete_multipart_xml(parts),
            expired=1200,
        )
        root = _parse_xml(response.content)
        _find_required_text(root, "ETag")

    async def abort_multipart_upload(self, key: str, upload_id: str) -> None:
        await self._request(
            method="DELETE",
            key=key,
            params={"uploadId": upload_id},
        )
