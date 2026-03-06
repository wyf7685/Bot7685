import contextlib
from collections.abc import AsyncIterator
from typing import Annotated

import nonebot_plugin_waiter.unimsg as waiter
from nonebot import get_driver
from nonebot.adapters import Event
from nonebot.params import Depends
from nonebot_plugin_alconna import Match, MsgTarget, UniMessage
from nonebot_plugin_alconna.uniseg import Receipt
from nonebot_plugin_uninfo import Uninfo

from .data_source import Repos

processing_repos: set[Repos] = set()


def schedule_recall(receipt: Receipt) -> None:
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

    approval_words = {"同意", "批准", "通过", "y", "yes", "approve"}
    rejection_words = {"拒绝", "不同意", "驳回", "n", "no", "reject", "refuse"}
    keywords = approval_words | rejection_words

    async def _rule(event: Event, t: MsgTarget, s: Uninfo) -> bool:
        if not t.verify(target):  # 同会话
            return False
        if s.member and s.member.role and s.member.role.level > 1:  # 管理员权限
            return False
        if event.get_plaintext().strip().lower() not in keywords:
            await UniMessage.text("请回复同意或拒绝").send(reply_to=True)
            return False
        return True

    @waiter.waiter(waits=[type(event)], rule=_rule)
    def wait(event: Event) -> bool:
        return event.get_plaintext().strip().lower() in approval_words

    result = await wait.wait(default=False, timeout=30)
    schedule_recall(receipt)
    return result


async def _extract_repository(
    event: Event,
    session: Uninfo,
    target: MsgTarget,
    owner: Match[str],
    repo: Match[str],
) -> AsyncIterator[Repos]:
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

    if repos in processing_repos:
        await UniMessage.text("该仓库正在被访问，请稍后再试").finish(reply_to=True)
    try:
        processing_repos.add(repos)
        yield repos
    finally:
        processing_repos.discard(repos)


Repository = Annotated[Repos, Depends(_extract_repository)]
