from collections.abc import Sequence

from nonebot_plugin_orm import Model, get_scoped_session
from sqlalchemy import Integer, String, delete, func, insert, select, update
from sqlalchemy.orm import Mapped, mapped_column


class ArkAccount(Model):
    uid: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        primary_key=True,
        unique=True,
    )
    """ 游戏角色 `uid` """
    token: Mapped[str] = mapped_column(String(32))
    """ 鹰角网络通行证 `token` """
    user_id: Mapped[int] = mapped_column(Integer())
    """ 用户ID """

    def __hash__(self) -> int:
        return hash(f"ArkAccount(uid={self.uid})")


class ArkAccountDAO:
    def __init__(self) -> None:
        self.session = get_scoped_session()

    async def is_uid_exists(self, uid: str) -> bool:
        statement = select(func.count(ArkAccount.uid)).where(ArkAccount.uid == uid)
        result = await self.session.execute(statement)
        return result.scalars().one() > 0

    async def save_account(self, user_id: int, token: str, uid: str) -> None:
        statement = (
            update(ArkAccount).where(ArkAccount.uid == uid)
            if await self.is_uid_exists(uid)
            else insert(ArkAccount)
        ).values(
            user_id=user_id,
            uid=uid,
            token=token,
        )

        await self.session.execute(statement)
        await self.session.commit()

    async def get_accounts(self, user_id: int | None = None) -> Sequence[ArkAccount]:
        statement = select(ArkAccount)
        if user_id is not None:
            statement = statement.where(ArkAccount.user_id == user_id)
        result = await self.session.execute(select(ArkAccount))
        return result.scalars().all()

    async def delete_account_by_uid(self, uid: str) -> None:
        if await self.is_uid_exists(uid):
            statement = delete(ArkAccount).where(ArkAccount.uid == uid)
            await self.session.execute(statement)
            await self.session.commit()

    async def delete_account(self, account: ArkAccount) -> None:
        await self.delete_account_by_uid(account.uid)

    async def load_account_by_uid(self, uid: str) -> ArkAccount | None:
        if await self.is_uid_exists(uid):
            statement = select(ArkAccount).where(ArkAccount.uid == uid)
            result = await self.session.execute(statement)
            return result.scalars().one()
        return None
