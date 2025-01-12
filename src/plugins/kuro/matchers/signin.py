from nonebot_plugin_alconna.uniseg import UniMessage

from ..handler import KuroHandler
from ..kuro_api import GameId
from .alc import root_matcher
from .depends import KuroTokenFromKey, KuroUserName

matcher_signin = root_matcher.dispatch("signin")


@matcher_signin.assign("~kuro")
async def assign_kuro(kuro_token: KuroTokenFromKey, name: KuroUserName) -> None:
    msg = UniMessage.text(f"开始执行库街区签到: {name}\n\n")
    await KuroHandler(kuro_token.token, msg).kuro_signin()
    await msg.send()


@matcher_signin.assign("~pns")
async def assign_pns(kuro_token: KuroTokenFromKey, name: KuroUserName) -> None:
    msg = UniMessage.text(f"开始执行战双游戏签到: {name}\n\n")
    await KuroHandler(kuro_token.token, msg).game_signin(GameId.PNS)
    await msg.send()


@matcher_signin.assign("~wuwa")
async def assign_wuwa(kuro_token: KuroTokenFromKey, name: KuroUserName) -> None:
    msg = UniMessage.text(f"开始执行鸣潮游戏签到: {name}\n\n")
    await KuroHandler(kuro_token.token, msg).game_signin(GameId.WUWA)
    await msg.send()
