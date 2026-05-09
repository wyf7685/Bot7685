from sqlalchemy import BLOB, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class KVStoreEntry(Base):
    __tablename__ = "kv_store_entry"

    plugin_id: Mapped[str] = mapped_column(String(64), primary_key=True, index=True)
    key: Mapped[str] = mapped_column(String(256), primary_key=True, index=True)
    value: Mapped[bytes] = mapped_column(BLOB)
