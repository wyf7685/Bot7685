from nonebot_plugin_alconna.uniseg import UniMessage

from ..handler import KuroHandler
from .alc import root_matcher
from .depends import KuroTokenFromKey

matcher_energy = root_matcher.dispatch("energy")


@matcher_energy.assign("~")
async def assign_energy(kuro_token: KuroTokenFromKey) -> None:
    msg = UniMessage()
    await KuroHandler(kuro_token.token, msg).check_energy(do_refresh=True)
    await msg.send()
