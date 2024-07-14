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
        async def build_ark(
            self,
            template_id: int,
            data: dict[str, str | list[dict[str, str]]],
        ) -> MessageArk:
            ark = MessageArk(template_id=template_id, kv=(kv := []))
            for key, val in data.items():
                if isinstance(val, str):
                    kv.append(MessageArkKv(key=key, value=val))
                elif isinstance(val, list):
                    kv.append(MessageArkKv(key=key, obj=(obj := [])))
                    for okvd in val:
                        obj.append(MessageArkObj(obj_kv=(okv := [])))
                        for k, v in okvd.items():
                            okv.append(MessageArkObjKv(key=k, value=v))
            return ark

        @descript(
            description="发送ark卡片",
            parameters=dict(ark="通过build_ark构建的ark结构体"),
        )
        @debug_log
        async def send_ark(self, ark: MessageArk) -> None:
            assert isinstance(self.event, Event)
            await cast(Bot, self.bot).send(self.event, MessageSegment.ark(ark))

        @override
        def export_to(self, context: T_Context) -> None:
            super(API, self).export_to(context)
            context["Message"] = Message
            context["MessageSegment"] = MessageSegment
