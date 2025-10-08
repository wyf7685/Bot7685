from typing import TYPE_CHECKING, final

from nonebot_plugin_orm import Model, get_scoped_session, get_session
from nonebot_plugin_uninfo.orm import UserModel, get_user_model
from nonebot_plugin_uninfo.target import to_target
from sqlalchemy import JSON, ForeignKey, Integer, String, or_, select
from sqlalchemy.orm import Mapped, mapped_column

if TYPE_CHECKING:
    from collections.abc import Sequence

    from nonebot_plugin_alconna.uniseg import Target
    from nonebot_plugin_uninfo.model import BasicInfo


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


@final
class KuroTokenDAO:
    def __init__(self, user_id: int, basic_info: BasicInfo) -> None:
        self.user_id = user_id
        self._basic = basic_info
        self._db_session = get_scoped_session()

    async def list_token(self, *, all: bool = False) -> Sequence[KuroToken]:  # noqa: A002
        stmt = select(KuroToken)
        if not all:
            stmt = stmt.where(KuroToken.user_id == self.user_id)
        result = await self._db_session.execute(stmt)
        return result.scalars().all()

    async def add(self, kuro_id: int, token: str, note: str | None = None) -> None:
        item = KuroToken(
            kuro_id=kuro_id,
            user_id=self.user_id,
            basic_info=self._basic,
            token=token,
            note=note,
        )

        self._db_session.add(item)
        await self._db_session.commit()

    async def find_token(self, key: str | None = None) -> KuroToken | None:
        stmt = select(KuroToken).where(KuroToken.user_id == self.user_id)
        if key is not None:
            where = KuroToken.note == key
            if key.isdigit():
                where = or_(where, KuroToken.kuro_id == int(key))
            stmt = stmt.where(where)

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


async def get_target(kuro_token: KuroToken) -> Target:
    user_model = await get_user_model(kuro_token.user_id)
    return to_target(await user_model.to_user(), kuro_token.basic_info)
