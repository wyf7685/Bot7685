from typing import Annotated, NamedTuple

from nonebot.params import Depends
from nonebot_plugin_alconna import Match, UniMessage


class OwnerRepo(NamedTuple):
    owner: str
    repo: str


async def _owner_repo(owner: Match[str], repo: Match[str]) -> OwnerRepo:
    if not owner.available or not repo.available:
        # TODO: read from database
        await UniMessage.text("请指定仓库的 owner 和 repo").finish(reply_to=True)

    return OwnerRepo(owner=owner.result, repo=repo.result)


Repository = Annotated[OwnerRepo, Depends(_owner_repo)]
