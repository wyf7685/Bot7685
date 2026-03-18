def apply() -> None:
    import nonebot

    from .cache import redis_config

    if redis_config is None:
        return

    try:
        from githubkit import Config
        from githubkit.cache.redis import AsyncRedisCacheStrategy
        from nonebot.adapters.github import Bot
        from redis.asyncio import Redis as AsyncRedis
    except ImportError:
        return

    redis = AsyncRedis(
        host=redis_config.host,
        port=redis_config.port,
        db=redis_config.db,
        password=redis_config.password,
    )
    cache_strategy = AsyncRedisCacheStrategy(redis, prefix="bot7685:githubkit:")

    @nonebot.get_driver().on_bot_connect
    async def _(bot: Bot) -> None:
        bot.github.config = Config(
            **{**bot.github.config.dict(), "cache_strategy": cache_strategy}
        )


apply()
