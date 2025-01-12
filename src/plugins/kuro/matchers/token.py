from types import EllipsisType

from nonebot_plugin_alconna import Query
from nonebot_plugin_alconna.uniseg import UniMessage
from nonebot_plugin_uninfo import Uninfo
from nonebot_plugin_waiter import prompt

from ..database.kuro_token import KuroTokenDAO
from ..kuro_api import KuroApi, KuroApiException
from .alc import root_matcher
from .depends import IsSuperUser, TokenDAO, TokenFromKey

matcher_token = root_matcher.dispatch("token")


async def prompt_input_token() -> str:
    msg = await prompt("请发送库街区token\n发送“取消”以取消操作")
    if msg is None:
        await UniMessage.text("等待超时").finish()

    text = msg.extract_plain_text()
    if text == "取消":
        await UniMessage.text("操作已取消").finish()

    return text


@matcher_token.assign("~add")
async def assign_add(
    session: Uninfo,
    token: str | EllipsisType = ...,
    note: str | None = None,
) -> None:
    if token is ...:
        token = await prompt_input_token()

    try:
        mine = await KuroApi(token).mine()
    except KuroApiException as err:
        await UniMessage.text(f"token 检查失败: {err.msg}").finish()

    ktd = KuroTokenDAO(session)

    for kuro_token in await ktd.list_token():
        if kuro_token.kuro_id == mine.userId:
            await UniMessage.text(f"库洛 ID {mine.userId} 已被绑定，请检查").finish()

    await ktd.add(mine.userId, token, note)
    await UniMessage.text(
        "添加成功\n"
        f"昵称: {mine.userName}\n"
        f"库洛 ID: {mine.userId}\n"
        f"备注: {note or "无"}"
    ).finish()


@matcher_token.assign("~remove")
async def assign_remove(session: Uninfo, key: str) -> None:
    ktd = KuroTokenDAO(session)
    if (kuro_token := await ktd.find_token(key)) is None:
        await UniMessage.text(f"未找到 {key} 对应的库洛账号").finish()

    kuro_id = kuro_token.kuro_id
    await ktd.remove(kuro_token)
    await UniMessage.text(f"已删除库洛账号 {kuro_id}").finish()


@matcher_token.assign("~list")
async def assign_list(
    session: Uninfo,
    is_super_user: IsSuperUser,
    all: Query[bool] = Query("~list.all.value"),  # noqa: A002, B008
) -> None:
    if all.result and not is_super_user:
        await UniMessage.text("你无权查看全部账号列表！").finish()

    ktd = KuroTokenDAO(session)
    tokens = await ktd.list_token(all=all.result)

    if not tokens:
        await UniMessage.text("未绑定任何库洛账号").finish()

    msg = UniMessage.text("库洛账号绑定列表:\n\n")
    for kuro_token in tokens:
        msg.text(f"库洛 ID: {kuro_token.kuro_id}\n").text(
            f"备注: {kuro_token.note or '无'}\n\n"
        )

    await msg.finish()


@matcher_token.assign("~update")
async def assign_update(
    ktd: TokenDAO,
    kuro_token: TokenFromKey,
    token: str | EllipsisType = ...,
    note: str | None = None,
) -> None:
    if token is ... and note is None:
        await UniMessage.text("请提供要更新的内容").finish()

    kuro_id = kuro_token.kuro_id

    if token is not ...:
        try:
            await KuroApi(token).mine()
        except KuroApiException as err:
            await UniMessage.text(f"token 检查失败: {err.msg}").finish()
        else:
            kuro_token.token = token

    if note is not None:
        kuro_token.note = note

    await ktd.update(kuro_token)
    await (
        UniMessage.text("库洛账号信息已更新\n\n")
        .text(f"库洛 ID: {kuro_id}\n")
        .text(f"备注: {note or '无'}")
        .finish()
    )
