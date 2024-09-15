from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import time
import urllib.parse
from copy import deepcopy
from typing import Any, Self

import httpx
from nonebot import logger

from .const import (
    HEADERS,
    HEADERS_EXCHANGE_CODE,
    HEADERS_LOGIN,
    HEADERS_SIGN,
    URL_BASIC_INFO,
    URL_BINDING,
    URL_EXCHANGE_CODE,
    URL_GEN_CRED,
    URL_GRANT_CODE,
    URL_SIGN,
    URL_TOKEN_PASSWORD,
    URL_USER_INFO,
)
from .database import ArkAccount, ArkAccountDAO
from .model import ArkUserInfo, BindInfo, DailySignAward, DailySignResult

logger = logger.opt(colors=True)


class SklandAPI:
    user_id: int
    client: httpx.AsyncClient
    token: str
    sign_token: str
    code: str
    cred: str
    uid: str

    @classmethod
    async def from_token(cls, user_id: int, token: str) -> Self | None:
        self = cls()
        self.user_id = user_id
        self.client = httpx.AsyncClient(headers=deepcopy(HEADERS))
        self.token = token

        if await self.get_code_by_token(self.token) is None:
            return
        if await self.get_cred_by_code(self.code) is None:
            return
        if (uid := await self.get_uid()) is None:
            return
        self.uid = uid
        return self

    @classmethod
    async def from_account(cls, account: ArkAccount) -> Self | None:
        return await cls.from_token(account.user_id, account.token)

    @classmethod
    async def from_phone_password(
        cls, user_id: int, phone: str, password: str
    ) -> Self | None:
        data = {"phone": phone, "password": password}

        async with httpx.AsyncClient(headers=HEADERS_LOGIN) as client:
            resp = await client.post(URL_TOKEN_PASSWORD, json=data)

        if not resp.is_success:
            logger.warning(f"获取 token({phone}) 失败: {resp} - {resp.text}")
            return

        res = resp.json()
        if res["status"] != 0:
            return

        return await cls.from_token(user_id, res["data"]["token"])

    async def save_account(self) -> None:
        await ArkAccountDAO().save_account(self.user_id, self.token, self.uid)

    async def destroy(self) -> None:
        if not self.client.is_closed:
            await self.client.aclose()

    def __del__(self, *_) -> None:
        asyncio.create_task(self.destroy())  # noqa: RUF006

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, exc_type, exc_value, traceback):
        await self.destroy()
        return exc_type, exc_value, traceback

    def _generate_signature(self, path: str, body: str) -> dict[str, str]:
        logger.debug(f"生成签名: path=<y>{path}</y>, body=<y>{body}</y>")
        timestamp = str(int(time.time()))
        logger.debug(f"签名时间戳: <c>{timestamp}</c>")

        headers = deepcopy(HEADERS_SIGN)
        headers["timestamp"] = timestamp
        s = path + body + timestamp + json.dumps(headers, separators=(",", ":"))
        logger.debug(f"签名字符串: <y>{s}</y>")

        key = self.sign_token.encode("utf-8")
        sig = hmac.new(key, s.encode("utf-8"), hashlib.sha256).hexdigest()
        md5 = hashlib.md5(sig.encode("utf-8")).hexdigest()
        headers["sign"] = md5
        logger.debug(f"签名md5: <y>{md5}</y>")

        return headers

    def _sign_headers(self, url: str, data: str | None) -> dict[str, str]:
        headers = deepcopy(HEADERS)
        del headers["cred"]
        urlp = urllib.parse.urlparse(url)
        if data is None:
            data = urlp.query
        headers.update(self._generate_signature(urlp.path, data))
        return headers

    async def get_code_by_token(self, token: str) -> str | None:
        data = {"token": token, "appCode": "4ca99fa6b56cc2ba", "type": 0}

        async with httpx.AsyncClient() as client:
            resp = await client.post(URL_GRANT_CODE, json=data)

        if not resp.is_success:
            logger.warning(f"获取 code 失败: {resp} - {resp.text}")
            return

        self.code = resp.json()["data"]["code"]
        return self.code

    async def get_cred_by_code(self, code: str) -> str | None:
        data = {"code": code, "kind": 1}

        resp = await self.client.post(URL_GEN_CRED, json=data)

        if not resp.is_success:
            logger.warning(f"获取 cred 失败: {resp} - {resp.text}")
            return

        res = resp.json()
        self.cred = res["data"]["cred"]
        self.client.headers["cred"] = self.cred
        self.sign_token = res["data"]["token"]
        return self.cred

    async def get_bind_info(self) -> list[BindInfo] | None:
        headers = dict(deepcopy(self.client.headers))
        headers.update(self._sign_headers(URL_BINDING, None))
        async with httpx.AsyncClient() as client:
            resp = await client.get(url=URL_BINDING, headers=headers)

        if not resp.is_success:
            logger.warning(f"获取用户绑定信息失败: {resp.text}")
            return

        j = resp.json()
        if j["code"] != 0:
            logger.warning(f"获取用户绑定信息失败: {j['message']}")
            return

        if data := j["data"]["list"]:
            return [
                BindInfo.model_validate(i) for i in data if i["appCode"] == "arknights"
            ]

    async def get_user_info(self) -> ArkUserInfo | None:
        headers = deepcopy(self.client.headers)
        headers.update(self._sign_headers(URL_USER_INFO, ""))
        resp = await self.client.get(url=URL_USER_INFO, headers=headers)

        if not resp.is_success:
            logger.warning(f"获取用户信息失败: {resp.text}")
            return

        return ArkUserInfo.model_validate((resp.json())["data"])

    async def get_uid(self) -> str | None:
        if bind := await self.get_bind_info():
            if uid := bind[0].defaultUid:
                return uid
            if items := bind[0].bindingList:
                return items[0].uid

    async def get_doctor_name(self, full: bool = False) -> str:
        if bind := await self.get_bind_info():
            if items := bind[0].bindingList:
                name = items[0].nickName
                if not full:
                    name = name.partition("#")[0]
                return name
        return "<获取失败>"

    async def get_phone(self) -> str | None:
        async with httpx.AsyncClient() as client:
            resp = await client.get(URL_BASIC_INFO, params={"token": self.token})

        if resp.is_success:
            return resp.json()["data"]["phone"]

    async def get_sign_data(self) -> dict[str, Any] | None:
        data = {"gameId": 1, "uid": self.uid}
        headers = deepcopy(self.client.headers)
        headers.update(self._sign_headers(URL_SIGN, f"gameId=1&uid={self.uid}"))
        resp = await self.client.get(URL_SIGN, params=data, headers=headers)

        try:
            res = resp.json()
        except Exception as err:
            logger.warning(f"json 序列化 sign 返回值时出现错误: {err}")
            return

        if res["code"] != 0:
            return

        return res["data"]

    async def daily_sign(self) -> DailySignResult:
        data = {"gameId": 1, "uid": self.uid}
        headers = deepcopy(self.client.headers)
        headers.update(self._sign_headers(URL_SIGN, json.dumps(data)))
        resp = await self.client.post(url=URL_SIGN, json=data, headers=headers)

        try:
            res = resp.json()
        except Exception as err:
            msg = f"json序列化 sign 返回值时出现错误: {err}"
            logger.warning(msg)
            return DailySignResult(status="failed", message=msg)

        if res["code"] != 0:
            return DailySignResult(status="failed", message=res["message"])

        return DailySignResult(
            status="success",
            message="success",
            awards=[
                DailySignAward(name=award["resource"]["name"], count=award["count"])
                for award in res["data"]["awards"]
            ],
        )

    async def exchange_code(self, giftCode: str):
        data = {
            "token": self.token,
            "giftCode": giftCode,
            "channelId": 1,
        }
        headers = deepcopy(HEADERS_EXCHANGE_CODE)
        resp = await self.client.post(
            url=URL_EXCHANGE_CODE,
            json=data,
            headers=headers,
        )

        try:
            res = resp.json()
        except Exception as err:
            msg = f"json序列化兑换码返回值时出现错误: {err}"
            logger.warning(msg)
            return False

        if res["code"] != 0:
            logger.warning(f"提交兑换码失败, 错误码 <y>{res['code']}</y>")
            logger.warning(f"错误信息: {res['msg']}")
            return False

        logger.success(f"兑换成功: <g>{res['data']['giftName']}</g>")
        return True
