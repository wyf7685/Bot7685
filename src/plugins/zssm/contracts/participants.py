from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Annotated, Protocol

from pydantic import StringConstraints

from ._validation import (
    _PARTICIPANT_ALIAS_PATTERN,
    _nonempty,
    _participant_alias,
)

ParticipantAlias = Annotated[
    str, StringConstraints(pattern=rf"^{_PARTICIPANT_ALIAS_PATTERN}$")
]


class ParticipantRole(StrEnum):
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"
    UNKNOWN = "unknown"


class ParticipantMetadataStatus(StrEnum):
    FULL = "full"
    PARTIAL = "partial"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class ParticipantRef:
    participant_alias: str
    raw_user_id: str = field(repr=False)
    is_invoker: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "participant_alias", _participant_alias(self.participant_alias)
        )
        if not self.raw_user_id:
            raise ValueError("raw_user_id must not be empty")


@dataclass(frozen=True, slots=True)
class ParticipantInfo:
    """The complete model-facing allowlist; deliberately contains no raw ID field."""

    participant_alias: str
    display_name: str
    scene_nickname: str | None
    account_name: str | None
    role: ParticipantRole
    is_invoker: bool
    metadata_status: ParticipantMetadataStatus

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "participant_alias", _participant_alias(self.participant_alias)
        )
        object.__setattr__(
            self, "display_name", _nonempty(self.display_name, "display_name")
        )
        for name in ("scene_nickname", "account_name"):
            if (value := getattr(self, name)) is not None:
                object.__setattr__(self, name, _nonempty(value, name))


class ParticipantResolver(Protocol):
    def observe(
        self, raw_user_id: str, *, is_invoker: bool = False
    ) -> ParticipantRef: ...
    def alias_for(self, raw_user_id: str) -> str | None: ...
    def ref_for_alias(self, participant_alias: str) -> ParticipantRef | None: ...
    async def resolve_known(
        self, participant_aliases: Sequence[str]
    ) -> tuple[ParticipantInfo, ...]: ...


__all__ = [
    "ParticipantAlias",
    "ParticipantInfo",
    "ParticipantMetadataStatus",
    "ParticipantRef",
    "ParticipantResolver",
    "ParticipantRole",
]
