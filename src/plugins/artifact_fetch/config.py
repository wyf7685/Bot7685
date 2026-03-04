from typing import Annotated

from githubkit import AppAuthStrategy, GitHub
from nonebot import get_bots, get_plugin_config
from nonebot.adapters.github import GitHubBot
from nonebot.matcher import Matcher
from nonebot.params import Depends
from pydantic import BaseModel, Field


class DownloadConfig(BaseModel):
    chunk_size: int = 1024 * 1024 * 1  # 1 MB
    concurrency_limit: int = 16


class PluginConfig(BaseModel):
    app_id: str | None = None
    download: DownloadConfig = Field(default_factory=DownloadConfig)


class Config(BaseModel):
    artifact_fetch: PluginConfig


plugin_config = get_plugin_config(Config).artifact_fetch


def get_github_bot() -> GitHubBot | None:
    return (
        bot
        if plugin_config.app_id is not None
        and (bot := get_bots().get(plugin_config.app_id))
        and isinstance(bot, GitHubBot)
        else None
    )


async def _bot_github() -> GitHub[AppAuthStrategy]:
    if bot := get_github_bot():
        return bot._github  # noqa: SLF001
    return Matcher.skip()


AppGitHub = Annotated[GitHub[AppAuthStrategy], Depends(_bot_github)]
