# ruff: noqa: N802, N815

import contextlib
import json
import warnings
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import ClassVar, Literal, cast, final, override

import httpx
from pydantic import TypeAdapter

from ..exceptions import ApiRequestFailed
from .headers import CommonRequestHeaders, RequestHeaders, WebRequestHeaders
from .response import Response, ValidResponseData
from .utils import ModelMixin


class DatetimeJsonEncoder(json.JSONEncoder):
    @override
    def default(self, o: object) -> object:
        if isinstance(o, datetime):
            return int(o.timestamp())
        if isinstance(o, timedelta):
            return o.total_seconds()
        return cast(object, json.JSONEncoder.default(self, o))


@final
@dataclass
class RequestInfo:
    url: str
    method: Literal["GET", "POST"] = "POST"


@dataclass
class Request[R: ValidResponseData](ModelMixin):
    _type_adapter: ClassVar[TypeAdapter[Response[ValidResponseData]] | None] = None
    _info_: ClassVar[RequestInfo]
    _resp_: ClassVar[type[ValidResponseData]]

    def _get_type_adapter(self) -> TypeAdapter[Response[R]]:
        cls = type(self)
        if cls._type_adapter is None:
            cls._type_adapter = TypeAdapter(Response[self._resp_])
        return cast(TypeAdapter[Response[R]], cls._type_adapter)

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
            except httpx.HTTPStatusError as err:
                raise ApiRequestFailed(str(response.status_code)) from err

        if isinstance(obj := data.get("data"), str):
            with contextlib.suppress(Exception):
                data["data"] = json.loads(obj)

        return self._get_type_adapter().validate_python(data, strict=False)


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
