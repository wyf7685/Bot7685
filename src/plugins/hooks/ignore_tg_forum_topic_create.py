from nonebot.adapters.telegram.event import ForumTopicCreatedEvent
from nonebot.exception import IgnoredException
from nonebot.message import event_preprocessor


@event_preprocessor
async def ignore_tg_forum_topic_create(_: ForumTopicCreatedEvent) -> None:
    raise IgnoredException("Ignore Telegram ForumTopicCreatedEvent")
