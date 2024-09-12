import asyncio
from datetime import datetime, timedelta
from random import Random
from typing import ClassVar

from nonebot.adapters.onebot.v11 import Bot

random = Random(__file__)
running_game: dict[int, "Game"] = {}


class Game:
    expire_time: ClassVar[timedelta] = timedelta(minutes=3)

    bot: Bot
    group_id: int
    total: int
    last_operation: datetime
    _cleanup_task: asyncio.Task[None]

    def __init__(self, bot: Bot, group_id: int) -> None:
        self.bot = bot
        self.group_id = group_id
        self.total = 6
        self.last_operation = datetime.now()
        self._cleanup_task = asyncio.create_task(self._cleanup())

    def shoot(self) -> bool:
        result = random.random() <= 1 / self.total
        self.total -= 1
        self.last_operation = datetime.now()
        return result

    def stop(self):
        self._cleanup_task.cancel()
        if self.group_id in running_game and running_game[self.group_id] is self:
            del running_game[self.group_id]

    async def _cleanup(self):
        while (  # noqa: ASYNC110
            datetime.now() - self.last_operation <= self.expire_time
        ):
            await asyncio.sleep(1)

        if self.group_id in running_game and running_game[self.group_id] is self:
            await self.bot.send_group_msg(group_id=self.group_id, message="游戏超时")
            del running_game[self.group_id]
