from nonebot_plugin_alconna import UniMessage

from ..kuro_api import GameId, KuroApiException
from ..kuro_api.calc import WuwaCalc
from .alc import root_matcher
from .depends import ApiFromKey, KuroUserName

matcher_phantom = root_matcher.dispatch("phantom")


@matcher_phantom.assign("~")
async def assign_phantom(
    api: ApiFromKey,
    user_name: KuroUserName,
    role_name: str,
) -> None:
    try:
        role_api = await api.get_default_role_api(GameId.WUWA)
    except KuroApiException as err:
        await UniMessage.text(f"获取鸣潮角色信息失败: {err}").finish()

    try:
        role_detail = await role_api.get_role_detail(role_name)
    except KuroApiException as err:
        await UniMessage.text(f"获取 {role_name!r} 角色详情失败: {err}").finish()

    result = WuwaCalc(role_detail).calc_phantom()

    # TODO: rewrite with htmlrender
    info = f"{user_name}: {role_detail.role.roleName}({role_detail.role.roleId})\n\n"
    if result := WuwaCalc(role_detail).calc_phantom():
        for idx, p in enumerate(result.phantoms, 1):
            pinfo = f" {p.name}: [{p.level}] {p.score}" if p else ": 未装配"
            info += f"声骸{idx}{pinfo}\n"
        info += f"\n总分: {result.total:.2f}"
    else:
        info += "角色声骸数据为空"

    await UniMessage.text(info).finish()
