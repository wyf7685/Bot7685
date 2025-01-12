import contextlib
import datetime
from collections.abc import Callable
from typing import Literal

import nonebot
import tzlocal
from nonebot_plugin_alconna.uniseg import Target, UniMessage

from .kuro_api import GameId, KuroApi, KuroApiException
from .kuro_api.api.gamer.role.list import WuwaRole

logger = nonebot.logger.opt(colors=True)
TZ = tzlocal.get_localzone()


def from_timestamp(timestamp: int, /) -> datetime.datetime:
    return datetime.datetime.fromtimestamp(timestamp, TZ)


class KuroHandler:
    api: KuroApi
    _msg: str = ""

    def __init__(self, api_or_token: KuroApi | str, /) -> None:
        if isinstance(api_or_token, KuroApi):
            self.api = api_or_token
        else:
            self.api = KuroApi(api_or_token)

    def log(
        self,
        text: str,
        log_meth: Callable[[str], object] = logger.info,
        /,
    ) -> None:
        self._msg += text + "\n"
        log_meth(text)

    def logln(self) -> None:
        self.log("")

    @property
    def msg(self) -> str:
        return self._msg.strip()

    async def push_msg(self, target: Target | None = None) -> None:
        await UniMessage.text(self.msg).send(target)
        self._msg = ""

    async def kuro_signin(self) -> None:
        self.log("执行库街区游戏签到...")

        try:
            await self.api.signin()
        except KuroApiException as err:
            self.log(f"库街区签到失败: {err.msg}", logger.warning)
            return

        self.log("库街区签到成功")

        try:
            gold_num = await self.api.get_gold_num()
        except KuroApiException as err:
            self.log(f"获取库洛币总数失败: {err.msg}", logger.warning)
            return

        self.log(f"当前库洛币总数: {gold_num}")

    async def game_signin(self, game_id: Literal[GameId.PNS, GameId.WUWA]) -> None:
        game_name = {GameId.PNS: "战双", GameId.WUWA: "鸣潮"}[game_id]
        self.log(f"执行{game_name}游戏签到...")

        try:
            roles = await self.api.role_list(game_id)
        except KuroApiException as err:
            self.log(f"获取{game_name}角色列表失败: {err.msg}", logger.warning)
            return

        if not roles:
            self.log(f"未绑定{game_name}角色")
            return

        for role in roles:
            role_api = self.api.get_role_api(role)
            try:
                result = await role_api.signin()
            except KuroApiException as err:
                self.log(f"{role.roleName}({role.roleId}) 签到失败: {err.msg}")
                return

            self.log(f"{role.roleName}({role.roleId}) 签到成功")
            for item in result:
                self.log(f" - {item.name} x{item.num}")

    async def do_signin(self) -> None:
        mine = await self.api.mine()  # 抛出错误由外层处理 XD
        self.log(f"开始执行签到: {mine.userName}({mine.userId})")
        self.logln()
        await self.kuro_signin()
        self.logln()
        await self.game_signin(GameId.PNS)
        self.logln()
        await self.game_signin(GameId.WUWA)
        self.logln()

    async def check_role_energy(self, role: WuwaRole) -> bool:
        try:
            widget = await self.api.get_role_api(role).get_widget_data()
        except KuroApiException as err:
            self.log(
                f"{role.roleName}({role.roleId}) 获取数据失败: {err.msg}",
                logger.warning,
            )
            return False

        energy = widget.energyData
        self.log(
            f"{role.roleName}({role.roleId}) "
            f"当前{energy.name}: {energy.cur}/{energy.total}"
        )
        if energy.total - energy.cur <= 5:
            return True

        if energy.refreshTimeStamp is not None:
            refresh = from_timestamp(energy.refreshTimeStamp)
            server_time = from_timestamp(widget.serverTime)
            if (delta := refresh - server_time).total_seconds() > 0:
                expected = (datetime.datetime.now(TZ) + delta).strftime("%H:%M:%S")
                self.log(f"预计恢复时间: {expected}")
                if delta.total_seconds() <= 60 * 30:
                    return True

        return False

    async def check_energy(self, *, do_refresh: bool = False) -> bool:
        mine = await self.api.mine()
        self.log(f"鸣潮结波晶片: {mine.userName}({mine.userId})")
        self.logln()

        try:
            roles = await self.api.role_list(GameId.WUWA)
        except KuroApiException as err:
            self.log(f"获取鸣潮角色列表失败: {err.msg}", logger.warning)
            return False

        if not roles:
            self.log("未绑定鸣潮角色")
            return False

        need_push = False

        for role in roles:
            if do_refresh:
                with contextlib.suppress(KuroApiException):
                    await self.api.get_role_api(role).refresh_data()
            need_push |= await self.check_role_energy(role)

        return need_push
