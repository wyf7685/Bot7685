import contextlib

import nonebot

with contextlib.suppress(ImportError):
    from .strategy import AsyncBotCacheStrategy, GitHubBot

    if "github" in map(str.lower, nonebot.get_adapters()):

        @nonebot.get_driver().on_bot_connect
        async def _(bot: GitHubBot) -> None:
            object.__setattr__(
                bot.github.config,
                "cache_strategy",
                AsyncBotCacheStrategy(f"githubkit:{bot.self_id}"),
            )
