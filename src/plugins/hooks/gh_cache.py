import nonebot

nonebot.require("src.service.cache")
from src.service.cache import redis_config


@nonebot.get_driver().on_startup
def setup_github_cache() -> None:
    if "github" not in map(str.lower, nonebot.get_adapters()):
        return
    if redis_config is None:
        return

    try:
        from githubkit import Config
        from githubkit.cache.redis import AsyncRedisCacheStrategy
        from nonebot.adapters.github import Bot
        from redis.asyncio import Redis as AsyncRedis
    except ImportError:
        return

    @nonebot.get_driver().on_bot_connect
    async def _(bot: Bot) -> None:
        assert redis_config is not None
        redis = AsyncRedis(
            host=redis_config.host,
            port=redis_config.port,
            db=redis_config.db,
            password=redis_config.password,
        )
        cache_strategy = AsyncRedisCacheStrategy(redis, prefix="bot7685:githubkit:")
        kwds = {**bot.github.config.dict(), "cache_strategy": cache_strategy}
        bot.github.config = Config(**kwds)
