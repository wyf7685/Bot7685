import base64

from nonebot.adapters.onebot import v11
from nonebot_plugin_alconna import UniMessage
from nonebot_plugin_localstore import get_plugin_data_dir

from ..kuro_api import KuroApiException, WuwaGachaApi
from ..kuro_api.gacha import WWGF
from .alc import root_matcher
from .depends import KuroTokenFromKey, convert_dependent

matcher = root_matcher.dispatch("gacha")
GACHA_DATA_DIR = get_plugin_data_dir() / "gacha"
GACHA_DATA_DIR.mkdir(parents=True, exist_ok=True)


@matcher.assign("~import")
async def assign_gacha_import(url: str) -> None:
    try:
        api = WuwaGachaApi(url)
    except KuroApiException as err:
        await matcher.finish(f"抽卡记录链接校验失败: {err.msg}")

    try:
        wwgf = await api.fetch_wwgf()
    except KuroApiException as err:
        await matcher.finish(f"获取抽卡记录失败: {err.msg}")

    new_record_count = wwgf.size

    gacha_file = GACHA_DATA_DIR / f"{wwgf.info.uid}.json"
    if gacha_file.exists():
        prev = WuwaGachaApi.load_file(gacha_file)
        stats = prev.merge(wwgf)
        new_record_count = stats.new
        wwgf = prev

    wwgf.dump_file(gacha_file)
    await matcher.finish(f"导入抽卡记录成功, 新增 {new_record_count} 条记录")


@convert_dependent
async def WWGFFromKey(kuro_token: KuroTokenFromKey) -> WWGF:  # noqa: N802
    gacha_file = GACHA_DATA_DIR / f"{kuro_token.user_id}.json"
    if not gacha_file.exists():
        await matcher.finish("未找到抽卡记录")

    return WuwaGachaApi.load_file(gacha_file)


@matcher.assign("~export")
async def assign_gacha_export_common(wwgf: WWGFFromKey) -> None:
    await matcher.send(f"UID: {wwgf.info.uid} \n抽卡记录数: {wwgf.size}")


@matcher.assign("~export")
async def assign_gacha_export_ob11(
    wwgf: WWGFFromKey,
    bot: v11.Bot,
    event: v11.GroupMessageEvent | v11.PrivateMessageEvent,
) -> None:
    params = {
        "name": f"{wwgf.info.uid}.json",
        "file": f"base64://{base64.b64encode(wwgf.dump().encode()).decode()}",
    }

    try:
        if isinstance(event, v11.GroupMessageEvent):
            await bot.upload_group_file(group_id=event.group_id, **params)
        else:
            await bot.upload_private_file(user_id=event.user_id, **params)
    except (v11.ActionFailed, v11.NetworkError) as err:
        await matcher.finish(f"上传抽卡记录失败: {err}")


@matcher.assign("~export")
async def assign_gacha_export_send(wwgf: WWGFFromKey) -> None:
    await UniMessage.file(
        raw=wwgf.dump().encode(),
        name=f"{wwgf.info.uid}.json",
    ).finish()


@matcher.assign("~")
async def assign_gacha(wwgf: WWGFFromKey) -> None:
    await matcher.send(
        f"UID: {wwgf.info.uid} \n抽卡记录数: {wwgf.size}\n\n抽卡分析待实现..."
    )
