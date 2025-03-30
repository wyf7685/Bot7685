# ruff: noqa: N802, N815

import contextlib
import dataclasses
import json
import warnings
from typing import ClassVar, Literal, cast, dataclass_transform, final, override

import httpx
from msgspec import json as msgjson
from pydantic import TypeAdapter

from ...exceptions import ApiRequestFailed, ApiResponseValidationFailed
from .headers import CommonRequestHeaders, RequestHeaders, WebRequestHeaders
from .response import Response, ValidResponseData


@final
@dataclasses.dataclass
class RequestInfo:
    url: str
    method: Literal["GET", "POST"] = "POST"


@dataclasses.dataclass
@dataclass_transform()
class Request[R: ValidResponseData]:
    _type_adapter: ClassVar[TypeAdapter[Response[ValidResponseData]] | None] = None
    _info_: ClassVar[RequestInfo]
    _resp_: ClassVar[type[ValidResponseData]]  # should be ClassVar[type[R]]

    @override
    def __init_subclass__(cls) -> None:
        super().__init_subclass__()
        _ = dataclasses.dataclass(cls)

    def dump(self) -> dict[str, object]:
        return msgjson.decode(msgjson.encode(dataclasses.asdict(self)))  # wtf

    @classmethod
    def _get_type_adapter(cls) -> TypeAdapter[Response[R]]:
        if cls._type_adapter is None:
            cls._type_adapter = TypeAdapter(Response[cls._resp_])
        return cast("TypeAdapter[Response[R]]", cls._type_adapter)

    def create_headers(self, token: str) -> RequestHeaders:
        return CommonRequestHeaders(token=token)

    async def send(self, token: str) -> Response[R]:
        headers = self.create_headers(token)

        async with httpx.AsyncClient(cookies=headers.get_cookies()) as client:
            try:
                response = await client.request(
                    method=self._info_.method,
                    url=self._info_.url,
                    headers=headers.dump(),
                    data=self.dump(),
                )
            except httpx.HTTPError as err:
                raise ApiRequestFailed(str(err)) from err

            try:
                data: dict[str, object] = response.raise_for_status().json()
            except (httpx.HTTPStatusError, json.JSONDecodeError) as err:
                raise ApiRequestFailed(str(response.status_code)) from err

        if isinstance(obj := data.get("data"), str):
            with contextlib.suppress(Exception):
                data["data"] = msgjson.decode(obj)

        try:
            return self._get_type_adapter().validate_python(data, strict=False)
        except ValueError as err:
            raise ApiResponseValidationFailed(
                f"接口返回值校验失败:\n{err}", data
            ) from err


class RequestWithoutToken[R: ValidResponseData](Request[R]):
    @override
    async def send(self, token: str | None = None) -> Response[R]:
        if token is not None:
            warnings.warn(f"token is not used in {type(self).__name__}", stacklevel=2)
        return await super().send("")


class WebRequest[R: ValidResponseData](Request[R]):
    @override
    def create_headers(self, token: str) -> RequestHeaders:
        return WebRequestHeaders(token=token)
