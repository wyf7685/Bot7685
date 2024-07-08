from nonebot.rule import Rule
from nonebot.adapters.onebot.v11 import GroupMessageEvent


async def _game_running(event: GroupMessageEvent):
    from .game import running_game

    return event.group_id in running_game


async def _game_not_running(event: GroupMessageEvent):
    return not await _game_running(event)


GameRunning = Rule(_game_running)
GameNotRunning = Rule(_game_not_running)
