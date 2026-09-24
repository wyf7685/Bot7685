from dataclasses import dataclass
from typing import Any

from ...contracts.web import MediaSetRef
from .sources.contracts import SourceAdapter, SourceTarget


@dataclass(frozen=True, slots=True)
class RegisteredMediaSet[T]:
    ref: MediaSetRef
    adapter: SourceAdapter[T]
    target: SourceTarget[T]


class InvocationMediaRegistry:
    """Invocation-local opaque handles for source-owned image collections."""

    def __init__(self) -> None:
        self._next_id = 1
        self._by_id: dict[str, RegisteredMediaSet[Any]] = {}
        self._by_key: dict[tuple[str, str], RegisteredMediaSet[Any]] = {}

    def register[T](
        self,
        *,
        adapter: SourceAdapter[T],
        target: SourceTarget[T],
        count: int,
        restricted: bool,
    ) -> MediaSetRef:
        if count <= 0:
            raise ValueError("media count must be positive")
        key = (adapter.source_id, target.canonical_url)
        if existing := self._by_key.get(key):
            return existing.ref
        media_id = f"m{self._next_id}"
        self._next_id += 1
        ref = MediaSetRef(media_id=media_id, count=count, restricted=restricted)
        registered = RegisteredMediaSet(ref=ref, adapter=adapter, target=target)
        self._by_id[media_id] = registered
        self._by_key[key] = registered
        return ref

    def get(self, media_id: str) -> RegisteredMediaSet[object] | None:
        return self._by_id.get(media_id)


__all__ = ["InvocationMediaRegistry", "RegisteredMediaSet"]
