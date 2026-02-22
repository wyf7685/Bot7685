from typing import Annotated, Literal

from nonebot.adapters import Event
from nonebot.params import Depends
from nonebot_plugin_alconna import At, MsgTarget
from nonebot_plugin_uninfo import Uninfo
from nonebot_plugin_uninfo.orm import get_scene_persist_id

from ..config import TemplateConfig, UserConfig, templates, users
from .matcher import finish, prompt


async def scene_id(session: Uninfo) -> int:
    return await get_scene_persist_id(session.basic, session.scene)


SceneID = Annotated[int, Depends(scene_id)]


async def _query_target_cfgs(
    event: Event,
    uni_target: MsgTarget,
    sid: SceneID,
    target: At | Literal["$group"] | None = None,
) -> list[UserConfig]:
    if target == "$group" and uni_target.private:
        await finish("请在群聊中使用 $group 参数")

    if target == "$group":
        cfgs = [
            cfg
            for cfg in users.load()
            if cfg.target.verify(uni_target) or sid in cfg.bind_groups
        ]
        if not cfgs:
            await finish("群内没有用户绑定账号")
        return cfgs

    user_id = event.get_user_id() if target is None else target.target
    cfgs = [cfg for cfg in users.load() if cfg.user_id == user_id]
    if not cfgs:
        await finish("用户没有绑定任何账号，请先使用 wplace bind 绑定")
    return cfgs


QueryConfigs = Annotated[list[UserConfig], Depends(_query_target_cfgs)]


async def _select_cfg(
    event: Event,
    identifier: str | None = None,
) -> UserConfig:
    user_id = event.get_user_id()
    user_cfgs = [cfg for cfg in users.load() if cfg.user_id == user_id]
    if not user_cfgs:
        await finish("你还没有绑定任何账号")

    if identifier is not None:
        gen = (
            cfg
            for cfg in filter(lambda c: c.wp_user_id, user_cfgs)
            if str(cfg.wp_user_id) == identifier or identifier in cfg.wp_user_name
        )
        if cfg := next(gen, None):
            return cfg
        await finish("未找到对应的绑定账号")

    if len(user_cfgs) == 1:
        return user_cfgs[0]

    formatted_cfgs = "".join(
        f"{i}. {cfg.wp_user_name} #{cfg.wp_user_id}\n"
        for i, cfg in enumerate(user_cfgs, start=1)
    )
    msg = "你绑定了多个账号，请回复要操作的账号序号:\n" + formatted_cfgs

    while True:
        text = await prompt(msg)
        if text.isdigit() and 1 <= (idx := int(text)) <= len(user_cfgs):
            return user_cfgs[idx - 1]
        msg = "无效的序号，请重新输入:\n" + formatted_cfgs


SelectedUserConfig = Annotated[UserConfig, Depends(_select_cfg)]


async def _target_template_cfg(sid: SceneID) -> TemplateConfig:
    cfgs = templates.load()
    if sid not in cfgs:
        await finish("当前会话没有绑定模板，请先使用 wplace template bind 绑定")
    return cfgs[sid]


TargetTemplate = Annotated[TemplateConfig, Depends(_target_template_cfg)]
