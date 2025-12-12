import datetime as dt

from nonebot.matcher import current_bot
from nonebot_plugin_alconna import At, Image, Reply, UniMessage
from nonebot_plugin_chatrecorder import MessageRecord, get_message_records
from nonebot_plugin_chatrecorder.message import deserialize_message
from nonebot_plugin_orm import get_session
from nonebot_plugin_uninfo import Session
from nonebot_plugin_uninfo.orm import SessionModel, UserModel
from sqlalchemy import select

from .schema import (
    AnalyzerInput,
    ChatInfo,
    ContentInfo,
    Message,
    MessageElement,
    RawMessage,
    ReplyInfo,
    SenderInfo,
    TextElement,
)

UTC8 = dt.timezone(dt.timedelta(hours=8))


def convert_messagerecord_to_analyzer_input(
    name: str,
    records: list[MessageRecord],
    user_id_map: dict[int, str],
    user_name_map: dict[int, str],
) -> AnalyzerInput:
    messages: list[Message] = []

    for record in records:
        if record.type == "message_sent":
            continue
        spid = record.session_persist_id
        sender_uin = user_id_map.get(spid, spid)
        sender_name = user_name_map.get(spid, str(sender_uin))
        sender = SenderInfo(uin=sender_uin, name=sender_name)
        content = ContentInfo(text=record.plain_text or "", reply=None)
        raw = RawMessage(subMsgType=0, sendMemberName=sender_name, elements=[])

        unimsg = UniMessage.of(deserialize_message(current_bot.get(), record.message))
        for seg in unimsg[At]:
            element = MessageElement(
                elementType=1,
                textElement=TextElement(atType=1, atUid=str(seg.target)),
            )
            raw.elements.append(element)
        for seg in unimsg[Image]:
            content.text += f"[图片:{seg.id}]"
        for seg in unimsg[Reply]:
            content.reply = content.reply or ReplyInfo(referencedMessageId=seg.id)

        message = Message(
            messageId=record.message_id,
            sender=sender,
            content=content,
            timestamp=record.time.strftime("%Y-%m-%d %H:%M:%S"),
            rawMessage=raw,
        )

        messages.append(message)

    return AnalyzerInput(messages=messages, chatName=name, chatInfo=ChatInfo(name=name))


async def fetch_analyzer_input(
    session: Session,
    year: int | None = None,
) -> AnalyzerInput:
    now = dt.datetime.now()
    if year is None or year == now.year:
        time_start = dt.datetime(now.year, 1, 1, tzinfo=UTC8)
        time_end = dt.datetime.now()
    else:
        time_start = dt.datetime(year, 1, 1, tzinfo=UTC8)
        time_end = dt.datetime(year + 1, 1, 1, tzinfo=UTC8)

    records = await get_message_records(
        session=session,
        filter_user=False,
        time_start=time_start,
        time_stop=time_end,
    )
    spids = {record.session_persist_id for record in records}

    async with get_session() as db_session:
        statement = (
            select(SessionModel.id, UserModel)
            .where(SessionModel.id.in_(spids))
            .join(SessionModel, UserModel.id == SessionModel.user_persist_id)
        )
        users = [row.tuple() for row in await db_session.execute(statement)]

    user_id_map = {sid: user.user_id for sid, user in users}
    user_name_map = {
        sid: (u := await user.to_user()).nick or u.name or u.id for sid, user in users
    }

    return convert_messagerecord_to_analyzer_input(
        name=session.scene.name or session.id,
        records=records,
        user_id_map=user_id_map,
        user_name_map=user_name_map,
    )
