from typing import Annotated

from nonebot.params import Depends
from nonebot_plugin_uninfo import Uninfo
from nonebot_plugin_uninfo.orm import get_scene_persist_id

from ..config import TemplateConfig, templates
from .matcher import finish


async def scene_id(session: Uninfo) -> int:
    return await get_scene_persist_id(session.basic, session.scene)


SceneID = Annotated[int, Depends(scene_id)]


async def _scene_template_cfg(sid: SceneID) -> TemplateConfig:
    cfgs = templates.load()
    if sid not in cfgs:
        await finish("当前会话没有绑定模板，请先使用 wplace template bind 绑定")
    return cfgs[sid]


SceneTemplate = Annotated[TemplateConfig, Depends(_scene_template_cfg)]
