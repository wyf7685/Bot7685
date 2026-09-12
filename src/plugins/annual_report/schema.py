from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class AnnualMessage:
    message_id: str
    sender_id: str | int
    sender_name: str
    text: str
    occurred_at: datetime
    reply_to_id: str | None = None
    at_user_ids: tuple[str, ...] = ()
    is_bot_message: bool = False


@dataclass(frozen=True, slots=True)
class AnalyzableText:
    sender_id: str | int
    text: str
