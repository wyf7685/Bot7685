import sqlalchemy as sa
from pydantic import TypeAdapter
from sqlalchemy.sql.elements import BooleanClauseList

from .database import get_session
from .model import KVStoreEntry


class KVStore:
    def __init__(self, plugin_id: str) -> None:
        self.plugin_id = plugin_id

    def _key_to_where_clause(self, key: str) -> BooleanClauseList:
        return (KVStoreEntry.plugin_id == self.plugin_id) & (KVStoreEntry.key == key)

    async def exists(self, key: str) -> bool:
        async with get_session() as session:
            result = await session.execute(
                sa.select(sa.func.count())
                .select_from(KVStoreEntry)
                .where(self._key_to_where_clause(key))
            )
            return result.scalar_one() > 0

    async def read_bytes(self, key: str) -> bytes:
        async with get_session() as session:
            result = await session.execute(
                sa.select(KVStoreEntry.value).where(self._key_to_where_clause(key))
            )
            entry = result.scalar_one_or_none()
        if entry is None:
            raise KeyError(f"Key '{key}' not found in KVStore.")
        return entry

    async def write_bytes(self, key: str, data: bytes) -> None:
        if await self.exists(key):
            async with get_session() as session:
                await session.execute(
                    sa.update(KVStoreEntry)
                    .where(self._key_to_where_clause(key))
                    .values(value=data)
                    .execution_options(synchronize_session="fetch")
                )
                await session.commit()
        else:
            async with get_session() as session:
                new_entry = KVStoreEntry(plugin_id=self.plugin_id, key=key, value=data)
                session.add(new_entry)
                await session.commit()

    async def delete(self, key: str) -> None:
        async with get_session() as session:
            await session.execute(
                sa.delete(KVStoreEntry).where(self._key_to_where_clause(key))
            )
            await session.commit()

    async def read_text(self, key: str, encoding: str = "utf-8") -> str:
        data = await self.read_bytes(key)
        return data.decode(encoding)

    async def write_text(self, key: str, text: str, encoding: str = "utf-8") -> None:
        data = text.encode(encoding)
        await self.write_bytes(key, data)

    def with_type[T](self, type_: type[T], /) -> TypedKVStore[T]:
        return TypedKVStore(self, type_)


class TypedKVStore[T]:
    def __init__(self, store: KVStore, type_: type[T]) -> None:
        self.store = store
        self._type_adapter = TypeAdapter(type_)

    async def exists(self, key: str) -> bool:
        return await self.store.exists(key)

    async def read(self, key: str) -> T:
        content = await self.store.read_bytes(key)
        return self._type_adapter.validate_json(content)

    async def write(self, key: str, value: T) -> None:
        content = self._type_adapter.dump_json(value)
        await self.store.write_bytes(key, content)

    async def delete(self, key: str) -> None:
        await self.store.delete(key)
