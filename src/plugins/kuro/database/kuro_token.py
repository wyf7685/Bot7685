from collections.abc import Sequence

from nonebot_plugin_orm import Model, get_scoped_session, get_session
from nonebot_plugin_uninfo import Session as UniSession
from nonebot_plugin_uninfo.model import BasicInfo
from nonebot_plugin_uninfo.orm import UserModel, get_user_persist_id
from sqlalchemy import JSON, ForeignKey, Integer, String, or_, select
from sqlalchemy.orm import Mapped, mapped_column


class KuroToken(Model):
    kuro_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey(UserModel.id),
        nullable=False,
    )
    basic_info: Mapped[BasicInfo] = mapped_column(JSON(), nullable=False)
    token: Mapped[str] = mapped_column(String(), nullable=False)
    note: Mapped[str | None] = mapped_column(String(), nullable=True)


class KuroTokenDAO:
    def __init__(self, session: UniSession) -> None:
        self.session = session
        self._user_id = None
        self._db_session = get_scoped_session()

    async def _get_user_id(self) -> int:
        if self._user_id is None:
            self._user_id = await get_user_persist_id(
                self.session.basic,
                self.session.user,
            )
        return self._user_id

    async def list_token(self, *, all: bool = False) -> Sequence[KuroToken]:
        stmt = select(KuroToken)
        if not all:
            stmt = stmt.where(KuroToken.user_id == await self._get_user_id())
        result = await self._db_session.execute(stmt)
        return result.scalars().all()

    async def add(self, kuro_id: int, token: str, note: str | None = None) -> None:
        item = KuroToken(
            kuro_id=kuro_id,
            user_id=await self._get_user_id(),
            basic_info=self.session.basic,
            token=token,
            note=note,
        )

        self._db_session.add(item)
        await self._db_session.commit()

    async def find_token(self, key: str) -> KuroToken | None:
        where = KuroToken.note == key
        if key.isdigit():
            where = or_(where, KuroToken.kuro_id == int(key))

        stmt = (
            select(KuroToken)
            .where(KuroToken.user_id == await self._get_user_id())
            .where(where)
        )

        result = await self._db_session.execute(stmt)
        return result.scalar_one_or_none()

    async def remove(self, kuro_token: KuroToken) -> None:
        await self._db_session.delete(kuro_token)
        await self._db_session.commit()

    async def update(self, kuro_token: KuroToken) -> None:
        await self._db_session.merge(kuro_token)
        await self._db_session.refresh(kuro_token)
        await self._db_session.commit()


async def list_all_token() -> Sequence[KuroToken]:
    async with get_session() as session:
        result = await session.execute(select(KuroToken))
        return result.scalars().all()
