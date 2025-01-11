from nonebot_plugin_alconna.uniseg import UniMessage

from ..kuro_api import GameId
from ..signin import LogFunc, game_signin, kuro_signin
from .alc import root_matcher
from .depends import ApiFromKey, KuroUserName

matcher_signin = root_matcher.dispatch("signin")


def log_wrapper(msg: UniMessage) -> LogFunc:
    return lambda line, *_: msg.text(f"{line}\n")


@matcher_signin.assign("~kuro")
async def assign_kuro(api: ApiFromKey, name: KuroUserName) -> None:
    msg = UniMessage.text(f"开始执行库街区签到: {name}\n\n")
    await kuro_signin(api, log_wrapper(msg))
    await msg.send()


@matcher_signin.assign("~pns")
async def assign_pns(api: ApiFromKey, name: KuroUserName) -> None:
    msg = UniMessage.text(f"开始执行战双游戏签到: {name}\n\n")
    await game_signin(api, GameId.PNS, log_wrapper(msg))
    await msg.send()


@matcher_signin.assign("~wuwa")
async def assign_wuwa(api: ApiFromKey, name: KuroUserName) -> None:
    msg = UniMessage.text(f"开始执行鸣潮游戏签到: {name}\n\n")
    await game_signin(api, GameId.WUWA, log_wrapper(msg))
    await msg.send()
