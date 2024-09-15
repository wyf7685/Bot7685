import asyncio
import random
from collections import defaultdict
from queue import Queue

import nonebot
from apscheduler.triggers.cron import CronTrigger
from nonebot_plugin_apscheduler import scheduler

from .api import SklandAPI
from .database import ArkAccount, ArkAccountDAO

logger = nonebot.logger.opt(colors=True)


async def sign(api: SklandAPI) -> None:
    name = await api.get_doctor_name(full=True)
    logger.info(f"森空岛签到: <y>Dr.</y> <c>{name}</c>")

    sign = await api.daily_sign()
    if sign.status == "failed":
        logger.info(f"签到失败: <b><r>{sign.message}</r></b>")
        return

    logger.info("签到成功, 获得物品:")
    for award in sign.awards:
        logger.info(f"    <g>{award.name}</g>×<y>{award.count}</y>")


async def sign_all() -> None:
    logger.info("森空岛全部签到开始")

    success = 0
    fail_count: dict[ArkAccount, int] = defaultdict(lambda: 0)
    que: Queue[ArkAccount] = Queue(0)

    for account in await ArkAccountDAO().get_accounts():
        que.put(account)

    while not que.empty():
        if sum(fail_count.values()) >= 5:
            logger.warning("签到失败次数达到 5 次，中止签到。")
            break
        if account := next(
            (account for account, count in fail_count.items() if count >= 3), None
        ):
            logger.warning(f"账号 {account} 签到失败次数达到 3 次，中止签到。")
            break

        delay = random.randint(5, 15)
        logger.info(f"等待 <y>{delay}</y> 秒...")
        await asyncio.sleep(delay)

        account = que.get()
        try:
            api = await SklandAPI.from_account(account)
        except Exception as e:
            logger.exception(f"加载森空岛账号 <c>{account.uid}</c> 错误")
            logger.exception(f"<r>{e.__class__.__name__}: {e}</r>")
            fail_count[account] += 1
            que.put(account)
            continue

        if not api:
            logger.info(f"加载森空岛账号 <c>{account.uid}</c> 失败")
            fail_count[account] += 1
            que.put(account)
            continue
        logger.info(f"加载森空岛账号: <c>{api.uid}</c>")

        try:
            await sign(api)
            await api.destroy()
        except Exception as e:
            logger.exception(f"森空岛账号 <c>{account.uid}</c> 签到出错")
            logger.exception(f"<r>{e.__class__.__name__}: {e}</r>")
            fail_count[account] += 1
            que.put(account)
            continue

        success += 1

    logger.success("森空岛全部签到结束")
    logger.info(f"成功 <y>{success}</y> 个, 失败 <y>{len(fail_count)}</y> 个")


logger.info("创建定时任务: <g>森空岛自动签到</g>")
scheduler.add_job(sign_all, CronTrigger(hour=6, minute=0, second=0))
