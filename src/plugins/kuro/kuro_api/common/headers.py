# ruff: noqa: N802, N815

import functools
from hashlib import sha256
from typing import Literal, override
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class RequestHeaders(BaseModel):
    def get_cookies(self) -> dict[str, str]:
        return {}

    def dump(self) -> dict[str, str]:
        return self.model_dump(mode="json", by_alias=True)


class CommonRequestHeaders(RequestHeaders):
    token: str
    # devCode: str
    # ip: str
    # distinct_id: str
    source: str = "android"
    version: str = "2.2.0"
    versionCode: str = "2200"
    osVersion: str = "Android"
    countryCode: str = "CN"
    model: str = "23127PN0CC"
    lang: str = "zh-Hans"
    channel_id: Literal["2"] = "2"
    content_type: str = Field(
        default="application/x-www-form-urlencoded", alias="Content-Type"
    )
    accept_encoding: str = Field(default="gzip", alias="Accept-Encoding")
    user_agent: str = Field(default="okhttp/3.11.0", alias="User-Agent")

    @functools.cached_property
    def devCode(self) -> str:
        s = self.token.encode() if self.token else uuid4().bytes
        return sha256(s).hexdigest()[:40].upper()

    @property
    def ip(self) -> str:
        h = sha256(self.token.encode()).hexdigest()
        return f"192.168.{int(h[:2],16)}.{int(h[2:4],16)}"

    @property
    def distinct_id(self) -> str:
        h = sha256(self.token.encode()).digest()
        return str(UUID(bytes=h[:16], version=4))

    @override
    def get_cookies(self) -> dict[str, str]:
        return {"user_token": self.token}

    @override
    def dump(self, *, without_distinct_id: bool = False) -> dict[str, str]:
        headers = super().dump()
        headers["devCode"] = self.devCode
        if self.token:
            headers["ip"] = self.ip
            if not without_distinct_id:
                headers["distinct_id"] = self.distinct_id
        return headers


_WEB_REQ_UA = (
    "Mozilla/5.0 (Linux; Android 14; 23127PN0CC Build/UKQ1.230804.001; wv)"
    " AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/128.0.6533.2"
    " Mobile Safari/537.36 Kuro/2.2.0 KuroGameBox/2.2.0"
)


class WebRequestHeaders(RequestHeaders):
    token: str
    pragma: str = "no-cache"
    cache_control: str = Field(default="no-cache", alias="cache-control")
    sec_ch_ua: str = Field(
        default='"Not)A;Brand";v="99", "Android WebView";v="128", "Chromium";v="128"',
        alias="sec-ch-ua",
    )
    source: str = "android"
    sec_ch_ua_mobile: str = Field(default="1", alias="sec-ch-ua-mobile")
    user_agent: str = Field(default=_WEB_REQ_UA, alias="user-agent")
    content_type: str = Field(
        default="application/x-www-form-urlencoded",
        alias="content-type",
    )
    accept: str = "application/json, text/plain, */*"
    devcode: str = f"114.51.41.91, {_WEB_REQ_UA}"
    sec_ch_ua_platform: str = Field(default='"Android"', alias="sec-ch-ua-platform")
    origin: str = "https://web-static.kurobbs.com"
    sec_fetch_site: str = Field(default="same-site", alias="sec-fetch-site")
    sec_fetch_mode: str = Field(default="cors", alias="sec-fetch-mode")
    sec_fetch_dest: str = Field(default="empty", alias="sec-fetch-dest")
    accept_encoding: str = Field(
        default="gzip, deflate, br, zstd",
        alias="accept-encoding",
    )
    accept_language: str = Field(
        default="zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
        alias="accept-language",
    )
    priority: str = Field(default="u=1, i")
    did: str = ""

    @override
    def get_cookies(self) -> dict[str, str]:
        return {"user_token": self.token}
