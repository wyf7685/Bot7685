from typing import overload

from nonebot.adapters import Bot

from . import common, discord, onebot11, telegram

processors = {
    None: common.MessageProcessor,
    "Discord": discord.MessageProcessor,
    "OneBot V11": onebot11.MessageProcessor,
    "Telegram": telegram.MessageProcessor,
}


@overload
def get_processor() -> type[common.MessageProcessor]: ...
@overload
def get_processor(adapter: str | None = None, /) -> type[common.MessageProcessor]: ...
@overload
def get_processor(src_bot: Bot) -> type[common.MessageProcessor]: ...
@overload
def get_processor(src_bot: Bot, dst_bot: Bot) -> common.MessageProcessor: ...


def get_processor(
    src_bot: Bot | str | None = None,
    dst_bot: Bot | None = None,
) -> type[common.MessageProcessor] | common.MessageProcessor:
    if dst_bot is not None:
        if not isinstance(src_bot, Bot):
            raise TypeError("src_bot must be Bot")
        return get_processor(src_bot)(src_bot, dst_bot)

    if isinstance(src_bot, Bot):
        src_bot = src_bot.type

    return processors.get(src_bot, common.MessageProcessor)
