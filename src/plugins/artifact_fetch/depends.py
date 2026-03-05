import contextlib
from typing import Annotated, NamedTuple

import nonebot_plugin_waiter.unimsg as waiter
from nonebot import get_driver
from nonebot.adapters import Event
from nonebot.params import Depends
from nonebot_plugin_alconna import Match, MsgTarget, UniMessage
from nonebot_plugin_alconna.uniseg import Receipt
from nonebot_plugin_uninfo import Uninfo


class Repos(NamedTuple):
    owner: str
    repo: str


def _lazy_recall(receipt: Receipt) -> None:
    async def recall() -> None:
        with contextlib.suppress(Exception):
            await receipt.recall()

    if receipt.recallable:
        get_driver().task_group.start_soon(recall)


async def _request_admin_approval(
    repos: Repos,
    event: Event,
    target: MsgTarget,
) -> bool:
    receipt = await (
        UniMessage.at(event.get_user_id())
        .text(f"\n用户请求访问仓库 {repos.owner}/{repos.repo}")
        .text("\n请管理员回复同意或拒绝")
    ).send(target)

    async def _rule(
        t: MsgTarget,
        s: Uninfo,
        # TODO: 检查是否为回复机器人消息
        # msg: UniMsg,
    ) -> bool:
        # 校验同会话
        if not t.verify(target):
            return False
        # 校验管理员权限
        return bool(s.member and s.member.role and s.member.role.level > 1)

    @waiter.waiter(waits=[type(event)], rule=_rule)
    def wait(event: Event) -> bool | None:
        text = event.get_plaintext().strip().lower()
        if text in {"同意", "批准", "通过", "y", "yes"}:
            return True
        if text in {"拒绝", "不同意", "驳回", "n", "no"}:
            return False
        return None

    async for result in wait(default=False):
        if result is None:
            await UniMessage.text("请回复同意或拒绝").send(reply_to=True)
            continue

        _lazy_recall(receipt)
        return result

    # Should never reach here, but just in case
    _lazy_recall(receipt)
    return False


async def _extract_repository(
    event: Event,
    session: Uninfo,
    target: MsgTarget,
    owner: Match[str],
    repo: Match[str],
) -> Repos:
    if not owner.available or not repo.available:
        # TODO: read from database
        await UniMessage.text("请指定仓库的 owner 和 repo").finish(reply_to=True)

    repos = Repos(owner=owner.result, repo=repo.result)

    if (
        # 在群组中, 且 uninfo 支持获取成员信息
        (member := session.member)
        # member 的 role level 始终等于 1
        and ((role := member.role) and role.level <= 1)
    ):
        # 普通群成员需要管理员审批
        approved = await _request_admin_approval(repos, event, target)
        if not approved:
            await UniMessage.text("管理员未通过你的请求").finish(reply_to=True)

    return repos


Repository = Annotated[Repos, Depends(_extract_repository)]
