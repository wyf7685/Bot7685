from nonebot import on_fullmatch
from nonebot.adapters.onebot.v11 import Bot, GroupMessageEvent, MessageSegment
from nonebot.rule import to_me

from .depends import GameNotRunning, GameRunning
from .game import Game, running_game

game_start = on_fullmatch("装弹", rule=to_me() & GameNotRunning)
game_shoot = on_fullmatch("开枪", rule=GameRunning)
game_stop = on_fullmatch("游戏结束", rule=to_me() & GameRunning)


@game_start.handle()
async def _(bot: Bot, event: GroupMessageEvent):
    game = Game(bot, event.group_id)
    running_game[event.group_id] = game
    msg = MessageSegment.reply(event.message_id) + (
        "当前群俄罗斯轮盘已开启\n"
        f"弹夹有 {game.total} 发子弹\n"
        "请发送 *开枪* 参与游戏"
    )
    await game_start.finish(msg)


@game_shoot.handle()
async def _(event: GroupMessageEvent):
    game = running_game[event.group_id]
    result = game.shoot()
    msg = (
        MessageSegment.at(event.user_id)
        + " 开了一枪，"
        + ("枪响了" if result else "枪没响")
        + f"\n当前剩余 {game.total} 发子弹"
    )
    await game_shoot.send(msg)

    if result:
        game.stop()
        await game_shoot.send("游戏结束")


@game_stop.handle()
async def _(event: GroupMessageEvent):
    running_game[event.group_id].stop()
    await game_stop.send("已中止当前群俄罗斯轮盘")