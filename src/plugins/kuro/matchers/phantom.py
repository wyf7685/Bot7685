from typing import TYPE_CHECKING

from nonebot_plugin_alconna import UniMessage

from ..kuro_api import GameId, KuroApiException
from ..kuro_api.calc import WuwaCalc
from .alc import root_matcher

if TYPE_CHECKING:
    from ..kuro_api.calc.calc import RolePhantomCalcResult
    from .depends import ApiFromKey, KuroUserName

matcher_phantom = root_matcher.dispatch("phantom")


def format_info(result: RolePhantomCalcResult, index: int | None) -> str:
    if not result.phantoms:
        return "角色声骸数据为空"

    if index is None:
        info = ""
        for idx, p in enumerate(result.phantoms, 1):
            pinfo = f" {p.name}: [{p.level}] {p.score}" if p else ": 未装配"
            info += f"声骸{idx}{pinfo}\n"
        info += f"\n总分: {result.total:.2f}"
        return info

    if not 1 <= index <= len(result.phantoms):
        return f"声骸序号 {index} 超出范围"

    if (p := result.phantoms[index - 1]) is None:
        return f"未装配声骸 {index}"

    info = f"声骸{index} {p.name}: [{p.level}] {p.score}\n\n"
    for prop in p.phantom.mainProps or []:
        info += f"{prop.attributeName}: {prop.attributeValue}\n"
    info += "\n"
    for prop in p.phantom.subProps or []:
        info += f"{prop.attributeName}: {prop.attributeValue}\n"
    return info


@matcher_phantom.assign("~")
async def assign_phantom(
    api: ApiFromKey,
    user_name: KuroUserName,
    role_name: str,
    index: int | None = None,
) -> None:
    try:
        role_api = await api.get_default_role_api(GameId.WUWA)
    except KuroApiException as err:
        await UniMessage.text(f"获取鸣潮角色信息失败: {err}").finish()

    try:
        role_detail = await role_api.get_role_detail(role_name)
    except KuroApiException as err:
        await UniMessage.text(f"获取 {role_name!r} 角色详情失败: {err}").finish()

    # TODO: rewrite with htmlrender
    info = f"{user_name}: {role_detail.role.roleName}({role_detail.role.roleId})\n\n"
    info += format_info(WuwaCalc(role_detail).calc_phantom(), index)
    await UniMessage.text(info).finish()
