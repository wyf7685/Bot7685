import anyio
from nonebot import get_driver, logger
from nonebot.adapters import Bot, Event
from nonebot.message import event_preprocessor
from nonebot_plugin_uninfo import Session, get_session

from src.utils import with_semaphore

from .config import config
from .detect import detect

driver = get_driver()
cache: dict[str, dict[str, int]] = {}
decrement_tasks: dict[str, tuple[int, anyio.CancelScope]] = {}


@event_preprocessor
async def before_event(bot: Bot, event: Event) -> None:
    try:
        event.get_message()
    except Exception:
        return

    try:
        session = await get_session(bot, event)
    except Exception:
        logger.opt(exception=True).debug("获取会话信息出错，跳过处理")
        return

    if session is None:
        logger.debug("获取会话信息失败，跳过处理")
        return

    if config.enabled_for(session):
        driver.task_group.start_soon(check_session, session)


def schedule_decrement(scene_id: str, user_id: str) -> None:
    amount = 1

    if (id := f"{scene_id}:{user_id}") in decrement_tasks:
        amount, scope = decrement_tasks[id]
        amount += 1
        scope.cancel()
        del decrement_tasks[id]

    @driver.task_group.start_soon
    async def _() -> None:
        with anyio.CancelScope() as scope:
            decrement_tasks[id] = (amount, scope)
            await anyio.sleep(config.trigger_delta)

        if scope.cancel_called or scope.cancelled_caught:
            return

        decrement_tasks.pop(id, None)
        if scene_id in cache and user_id in cache[scene_id]:
            cache[scene_id][user_id] -= amount
            if cache[scene_id][user_id] <= 0:
                del cache[scene_id][user_id]
                if not cache[scene_id]:
                    del cache[scene_id]


@with_semaphore(1)
async def check_session(session: Session) -> None:
    cache.setdefault(session.scene.id, {}).setdefault(session.user.id, 0)
    cache[session.scene.id][session.user.id] += 1
    schedule_decrement(session.scene.id, session.user.id)

    scene = cache[session.scene.id]
    if len(scene) >= config.user_threshold and any(
        count >= config.per_user_threshold for count in scene.values()
    ):

        @driver.task_group.start_soon
        async def _() -> None:
            try:
                await detect(session)
            except Exception:
                logger.exception(f"检测会话 {session.scene.id} 时发生错误")
