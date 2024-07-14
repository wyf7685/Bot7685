import contextlib
from typing import cast, override

from ...constant import T_Context
from ..api import API as BaseAPI
from ..api import register_api
from ..help_doc import descript, type_alias
from ..utils import debug_log

with contextlib.suppress(ImportError):
    from nonebot.adapters.qq import Adapter, Bot, Event, Message, MessageSegment
    from nonebot.adapters.qq.models import (
        MessageArk,
        MessageArkKv,
        MessageArkObj,
        MessageArkObjKv,
    )

    type_alias[Message] = "Message"
    type_alias[MessageSegment] = "MessageSegment"

    # fmt: off
    def build_ark(
        template_id: int,
        data: dict[str, str | list[dict[str, str]]],
    ) -> MessageArk:
        return MessageArk(template_id=template_id, kv=[
            MessageArkKv(key=key, value=val)
            if isinstance(val, str) else
            MessageArkKv(key=key, obj=[
                MessageArkObj(obj_kv=[
                    MessageArkObjKv(key=k, value=v)
                    for k, v in okvd.items()
                ])
                for okvd in val
            ])
            for key, val in data.items()
        ])
    # fmt: on

    @register_api(Adapter)
    class API(BaseAPI):
        @descript(
            description="构建ark结构体",
            parameters=dict(
                template_id="ark模板id, 目前可以为23/24/37",
                data="ark模板参数",
            ),
            result="ark结构体",
        )
        @debug_log
        def build_ark(
            self,
            template_id: int,
            data: dict[str, str | list[dict[str, str]]],
        ) -> MessageArk:
            return build_ark(template_id, data)

        @descript(
            description="发送ark卡片",
            parameters=dict(ark="通过build_ark构建的ark结构体"),
        )
        @debug_log
        async def send_ark(self, ark: MessageArk) -> None:
            assert isinstance(self.event, Event)
            await self._native_send(MessageSegment.ark(ark))

        @override
        def export_to(self, context: T_Context) -> None:
            super(API, self).export_to(context)
            context["Message"] = Message
            context["MessageSegment"] = MessageSegment
