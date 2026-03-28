from collections.abc import AsyncIterator
from typing import Annotated

import nonebot_plugin_waiter.unimsg as waiter
from nonebot.adapters import Event
from nonebot.params import Depends
from nonebot_plugin_alconna import Match, MsgTarget, UniMessage
from nonebot_plugin_uninfo import Uninfo

from src.utils import schedule_recall

from .data_source import Repos, subscriptions

processing_repos: set[Repos] = set()


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


async def _select_repos(
    target: MsgTarget,
    owner: Match[str],
    repo: Match[str],
) -> Repos:
    if owner.available and repo.available:
        return Repos(owner=owner.result, repo=repo.result)

    subs = [
        sub
        for sub in subscriptions.load()
        if sub.target.verify(target)
        and (not owner.available or sub.owner == owner.result)
        and (not repo.available or sub.repo == repo.result)
    ]
    if not subs:
        await UniMessage.text("请指定仓库的 owner 和 repo").finish(reply_to=True)

    if len(subs) == 1:
        return subs[0].repos

    formatted_subs = "\n".join(
        f"{idx}. {sub.owner}/{sub.repo}" for idx, sub in enumerate(subs, 1)
    )
    prompt = f"请回复要访问的仓库编号：\n\n{formatted_subs}"
    result = await waiter.prompt(prompt)
    if (
        result is None
        or not (text := result.extract_plain_text().strip()).isdigit()
        or not 1 <= (idx := int(text)) <= len(subs)
    ):
        await UniMessage.text("输入无效，操作已取消").finish(reply_to=True)

    return subs[idx - 1].repos


async def _extract_repository(
    event: Event,
    session: Uninfo,
    target: MsgTarget,
    repos: Annotated[Repos, Depends(_select_repos)],
) -> AsyncIterator[Repos]:
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
