from typing import Annotated, NoReturn

from nonebot import require
from nonebot.params import Depends

require("nonebot_plugin_alconna")
require("nonebot_plugin_apscheduler")
require("nonebot_plugin_orm")
require("nonebot_plugin_user")
require("nonebot_plugin_waiter")
import nonebot_plugin_waiter as waiter
from nonebot_plugin_alconna import (
    Alconna,
    Args,
    CommandMeta,
    Match,
    Subcommand,
    on_alconna,
)
from nonebot_plugin_alconna.uniseg import MsgTarget, UniMessage, UniMsg
from nonebot_plugin_user import User, get_user_by_id

from .api import SklandAPI
from .database import ArkAccount, ArkAccountDAO

skland = on_alconna(
    Alconna(
        "森空岛",
        Subcommand(
            "bind",
            Args["phone?", str],
            Args["password?", str],
            alias={"绑定", "登录", "登陆"},
        ),
        Subcommand("revoke", alias={"解绑", "登出"}),
        Subcommand("sign", alias={"签到"}),
        meta=CommandMeta(
            description="森空岛签到",
            usage="森空岛 -h",
            example="森空岛 绑定 12345678910 password\n森空岛 签到\n森空岛 解绑",
            author="wyf7685",
        ),
    ),
    aliases={"skland"},
)


@skland.assign("bind")
async def _(target: MsgTarget) -> None:
    if not target.private:
        await UniMessage.text("请在私聊发送命令绑定账号！").finish(reply_to=True)


def check_phone(phone: str) -> bool:
    return phone.isdigit() and len(phone) == 11 and phone[0] == "1"


@skland.assign("bind")
async def _(user: User, phone: Match[str], password: Match[str]) -> None:
    @waiter.waiter(["message"], keep_session=True)
    def wait(msg: UniMsg) -> str:
        return msg.extract_plain_text().strip()

    if not phone.available or not check_phone(phone.result):
        await UniMessage(
            "手机号格式错误，请重新发送" if phone.available else "请发送手机号"
        ).send()
        async for received in wait():
            if received is None:
                await UniMessage("输入超时，已自动取消").finish()
            if check_phone(received):
                phone.result = received
                break
            await UniMessage("手机号格式错误，请重新发送").send()

    if not password.available:
        await UniMessage.text("请发送密码").send()
        if (received := await wait.wait()) is None:
            await UniMessage("输入超时，已自动取消").finish()
        password.result = received

    api = await SklandAPI.from_phone_password(
        user_id=user.id,
        phone=phone.result,
        password=password.result,
    )

    if api is None:
        await UniMessage("登录失败！").finish()

    name = await api.get_doctor_name(full=True)

    if (
        account := await ArkAccountDAO().load_account_by_uid(api.uid)
    ) and account.user_id != user.id:
        await api.destroy()
        another = await get_user_by_id(account.user_id)
        await UniMessage(
            f"账号 {name} 已经被 {another.name}({another.id}) 绑定了"
        ).finish(reply_to=True)

    await api.save_account()
    await api.destroy()
    await UniMessage(f"登录成功: {name}").finish()


async def get_account(user: User) -> ArkAccount | None:
    return next(iter(await ArkAccountDAO().get_accounts(user.id)), None)


UserAccount = Annotated[ArkAccount | None, Depends(get_account)]


@skland.assign("revoke")
async def _(account: UserAccount) -> NoReturn:
    if not account:
        await UniMessage("你还没有绑定过森空岛账号").finish()

    info = account.uid
    api = await SklandAPI.from_account(account)
    if api is not None:
        info = await api.get_doctor_name(full=True)
        await api.destroy()

    await ArkAccountDAO().delete_account(account)
    await UniMessage(f"已解绑账号 {info}").finish()


@skland.assign("sign")
async def _(account: UserAccount) -> NoReturn:
    if not account:
        await UniMessage("你还没有绑定过森空岛账号").finish()

    api = await SklandAPI.from_account(account)
    if api is None:
        await ArkAccountDAO().delete_account(account)
        await UniMessage(f"账号 {account.uid} 登录失效，请重新绑定").finish()

    name = await api.get_doctor_name(full=True)
    msg = f"森空岛签到: Dr. {name}\n"

    sign = await api.daily_sign()
    if sign.status == "failed":
        msg += f"签到失败: {sign.message}"
        await UniMessage(msg).finish()

    msg += "签到成功, 获得物品:\n"
    for award in sign.awards:
        msg += f"    {award.name}×{award.count}"
    await UniMessage(msg).finish()
