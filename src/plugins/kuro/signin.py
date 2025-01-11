import random
from collections.abc import Callable
from typing import Literal, Protocol

import anyio
import nonebot
from apscheduler.triggers.cron import CronTrigger
from nonebot_plugin_alconna.uniseg import UniMessage
from nonebot_plugin_apscheduler import scheduler
from nonebot_plugin_uninfo.orm import get_user_model
from nonebot_plugin_uninfo.target import to_target

from .config import config
from .database.kuro_token import KuroToken, list_all_token
from .kuro_api import GameId, KuroApi, KuroApiException

logger = nonebot.logger.opt(colors=True)
trigger = CronTrigger(
    hour=config.auto_signin.hour,
    minute=config.auto_signin.minute,
)


class LogFunc(Protocol):
    def __call__(
        self,
        text: str,
        log_meth: Callable[[str], object] = ...,
        /,
    ) -> object: ...


async def kuro_signin(
    api: KuroApi,
    log: LogFunc = lambda *_: None,
) -> None:
    try:
        result = await api.signin()
    except KuroApiException as err:
        log(f"库街区签到失败: {err.msg}", logger.warning)
        return

    log("库街区签到成功")
    for item in result.gainVoList:
        log(f" - {item.gainTyp} x{item.gainValue}")

    try:
        gold_num = await api.get_gold_num()
    except KuroApiException as err:
        log(f"获取库洛币总数失败: {err.msg}", logger.warning)
        return

    log(f"当前库洛币总数: {gold_num}")


async def game_signin(
    api: KuroApi,
    game_id: Literal[GameId.PNS, GameId.WUWA],
    log: LogFunc = lambda *_: None,
) -> None:
    game_name = {GameId.PNS: "战双", GameId.WUWA: "鸣潮"}[game_id]

    try:
        roles = await api.role_list(game_id)
    except KuroApiException as err:
        log(f"获取{game_name}角色列表失败: {err.msg}", logger.warning)
        return

    if not roles:
        log(f"未绑定{game_name}角色")
        return

    for role in roles:
        try:
            result = await api.get_role_api(role).signin()
        except KuroApiException as err:
            log(f"{role.roleName}({role.roleId}) 签到失败: {err.msg}")
            return

        log(f"{role.roleName}({role.roleId}) 签到成功")
        for item in result:
            log(f" - {item.goodsId} x{item.goodsNum}")


async def do_signin(
    token: str,
) -> str:
    api = KuroApi(token)
    mine = await api.mine()  # 抛出错误由外层处理 XD

    msg = ""

    def log(text: str, log_meth: Callable[[str], object] = logger.info, /) -> None:
        nonlocal msg
        msg += text + "\n"
        log_meth(text)

    log(f"开始执行签到: {mine.userName}({mine.userId})")
    log("")
    await kuro_signin(api, log)
    log("")
    await game_signin(api, GameId.PNS, log)
    log("")
    await game_signin(api, GameId.WUWA, log)
    log("")

    return msg.strip()


async def notify_signin_result(kuro_token: KuroToken, msg: str) -> None:
    user_model = await get_user_model(kuro_token.user_id)
    target = to_target(await user_model.to_user(), kuro_token.basic_info)
    await UniMessage.text(msg).send(target)


@scheduler.scheduled_job(trigger, misfire_grace_time=60)
async def auto_signin() -> None:
    for kuro_token in await list_all_token():
        try:
            msg = await do_signin(kuro_token.token)
        except Exception as err:
            logger.opt(exception=err).warning(f"{kuro_token.kuro_id} 签到失败: {err}")
        else:
            try:
                await notify_signin_result(kuro_token, msg)
            except Exception as err:
                logger.opt(exception=err).warning(
                    f"{kuro_token.kuro_id} 发送通知失败: {err}"
                )
        finally:
            await anyio.sleep(random.randint(2, 5))
