import contextlib

import nonebot

with contextlib.suppress(ImportError):
    from .strategy import AsyncBotCacheStrategy, GitHubBot

    @nonebot.get_driver().on_startup
    def setup_github_cache() -> None:
        if "github" not in map(str.lower, nonebot.get_adapters()):
            return

        @nonebot.get_driver().on_bot_connect
        async def _(bot: GitHubBot) -> None:
            object.__setattr__(
                bot.github.config,
                "cache_strategy",
                AsyncBotCacheStrategy(f"githubkit:{bot.self_id}"),
            )
