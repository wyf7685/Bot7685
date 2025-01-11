# ruff: noqa: N802, N815

import contextlib
import dataclasses
import json
import warnings
from typing import ClassVar, Literal, cast, final, override

import httpx
from pydantic import BaseModel, TypeAdapter

from ..exceptions import ApiRequestFailed
from .headers import CommonRequestHeaders, RequestHeaders, WebRequestHeaders
from .response import Response, ValidResponseData


@final
@dataclasses.dataclass
class RequestInfo:
    url: str
    method: Literal["GET", "POST"] = "POST"


class Request[R: ValidResponseData](BaseModel):
    _type_adapter: ClassVar[TypeAdapter[Response[ValidResponseData]] | None] = None

    def _get_type_adapter(self) -> TypeAdapter[Response[R]]:
        cls = type(self)
        if cls._type_adapter is None:
            t = self.get_response_data_class()
            cls._type_adapter = TypeAdapter(Response[t])
        return cast(TypeAdapter[Response[R]], cls._type_adapter)

    def create_headers(self, token: str) -> RequestHeaders:
        return CommonRequestHeaders(token=token)

    def get_info(self) -> RequestInfo:
        raise NotImplementedError

    def get_response_data_class(self) -> type[R]:
        raise NotImplementedError

    async def send(self, token: str) -> Response[R]:
        info = self.get_info()
        headers = self.create_headers(token)

        async with httpx.AsyncClient(cookies=headers.get_cookies()) as client:
            try:
                response = await client.request(
                    method=info.method,
                    url=info.url,
                    headers=headers.dump(),
                    data=self.model_dump(mode="json", by_alias=True),
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
