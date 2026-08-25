from __future__ import annotations

import asyncio
import re
import secrets
import unicodedata
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, replace
from enum import Enum

from nonebot.adapters import Bot
from nonebot_plugin_orm import get_session
from nonebot_plugin_uninfo import Member, SceneType, Session, User, get_interface
from nonebot_plugin_uninfo.orm import BotModel, SceneModel, SessionModel, UserModel
from sqlalchemy import select

from src.service.llm.tools import BoundTool, JSONValue, ToolOutput

from ..config import ParticipantsConfig
from ..contracts import (
    ParticipantInfo,
    ParticipantInfoArgs,
    ParticipantMetadataStatus,
    ParticipantRef,
    ParticipantRole,
    ZssmToolContext,
    bind_participant_info_args,
)

_PARTICIPANT_ALIAS_RE = re.compile(r"^p_[0-9a-f]{16}$")
_BIDI_CONTROL_CLASSES = frozenset(
    {"BN", "LRE", "RLE", "LRO", "RLO", "LRI", "RLI", "FSI", "PDI", "PDF"}
)


@dataclass(frozen=True, slots=True)
class _MetadataSnapshot:
    user: User | None
    member: Member | None


class InvocationParticipantResolver:
    """Invocation-local mapping from private platform IDs to opaque aliases."""

    __slots__ = (
        "_bot",
        "_config",
        "_interface",
        "_lookup_locks",
        "_lookup_semaphore",
        "_metadata_cache",
        "_refs_by_alias",
        "_refs_by_raw_id",
        "_session",
    )

    def __init__(
        self,
        bot: Bot,
        session: Session,
        config: ParticipantsConfig,
    ) -> None:
        self._bot = bot
        self._session = session
        self._config = config
        self._interface = get_interface(bot)
        self._lookup_semaphore = asyncio.Semaphore(config.max_parallel_lookups)
        self._lookup_locks: dict[str, asyncio.Lock] = {}
        self._refs_by_raw_id: dict[str, ParticipantRef] = {}
        self._refs_by_alias: dict[str, ParticipantRef] = {}
        self._metadata_cache: dict[str, ParticipantInfo] = {}

    def observe(self, raw_user_id: str, *, is_invoker: bool = False) -> ParticipantRef:
        if not isinstance(raw_user_id, str):
            raise TypeError("raw_user_id must be a string")
        if not raw_user_id:
            raise ValueError("raw_user_id must not be empty")

        if current := self._refs_by_raw_id.get(raw_user_id):
            if is_invoker and not current.is_invoker:
                current = replace(current, is_invoker=True)
                self._refs_by_raw_id[raw_user_id] = current
                self._refs_by_alias[current.participant_alias] = current
                if cached := self._metadata_cache.get(raw_user_id):
                    self._metadata_cache[raw_user_id] = replace(
                        cached,
                        is_invoker=True,
                    )
            return current

        while True:
            participant_alias = f"p_{secrets.token_hex(8)}"
            if participant_alias not in self._refs_by_alias:
                break
        ref = ParticipantRef(
            participant_alias=participant_alias,
            raw_user_id=raw_user_id,
            is_invoker=is_invoker,
        )
        self._refs_by_raw_id[raw_user_id] = ref
        self._refs_by_alias[participant_alias] = ref
        return ref

    def alias_for(self, raw_user_id: str) -> str | None:
        ref = self._refs_by_raw_id.get(raw_user_id)
        return ref.participant_alias if ref is not None else None

    def ref_for_alias(self, participant_alias: str) -> ParticipantRef | None:
        return self._refs_by_alias.get(participant_alias)

    async def resolve_known(
        self,
        participant_aliases: Sequence[str],
    ) -> tuple[ParticipantInfo, ...]:
        entries: list[ParticipantRef | ParticipantInfo] = []
        refs: list[ParticipantRef] = []
        seen: set[str] = set()
        for participant_alias in participant_aliases:
            if participant_alias in seen:
                continue
            seen.add(participant_alias)
            if ref := self._refs_by_alias.get(participant_alias):
                entries.append(ref)
                refs.append(ref)
            elif _PARTICIPANT_ALIAS_RE.fullmatch(participant_alias):
                entries.append(
                    ParticipantInfo(
                        participant_alias=participant_alias,
                        display_name=participant_alias,
                        scene_nickname=None,
                        account_name=None,
                        role=ParticipantRole.UNKNOWN,
                        is_invoker=False,
                        metadata_status=ParticipantMetadataStatus.UNAVAILABLE,
                    )
                )

        resolved = await asyncio.gather(*(self._resolve_ref(ref) for ref in refs))
        by_alias = {info.participant_alias: info for info in resolved}
        return tuple(
            by_alias[entry.participant_alias]
            if isinstance(entry, ParticipantRef)
            else entry
            for entry in entries
        )

    async def _resolve_ref(self, ref: ParticipantRef) -> ParticipantInfo:
        raw_user_id = ref.raw_user_id
        if cached := self._metadata_cache.get(raw_user_id):
            if cached.is_invoker != ref.is_invoker:
                cached = replace(cached, is_invoker=ref.is_invoker)
                self._metadata_cache[raw_user_id] = cached
            return cached

        lock = self._lookup_locks.setdefault(raw_user_id, asyncio.Lock())
        async with lock:
            if cached := self._metadata_cache.get(raw_user_id):
                if cached.is_invoker != ref.is_invoker:
                    cached = replace(cached, is_invoker=ref.is_invoker)
                    self._metadata_cache[raw_user_id] = cached
                return cached

            info = await self._lookup_metadata(ref)
            latest_ref = self._refs_by_raw_id[raw_user_id]
            if info.is_invoker != latest_ref.is_invoker:
                info = replace(info, is_invoker=latest_ref.is_invoker)
            self._metadata_cache[raw_user_id] = info
            return info

    async def _lookup_metadata(self, ref: ParticipantRef) -> ParticipantInfo:
        raw_user_id = ref.raw_user_id
        scene = self._session.scene
        is_private_peer = (
            scene.type is SceneType.PRIVATE and raw_user_id == self._session.user.id
        )
        is_membership_scene = (
            scene.type is SceneType.GROUP or scene.type.value >= SceneType.GUILD.value
        )
        if not is_private_peer and not is_membership_scene:
            return ParticipantInfo(
                participant_alias=ref.participant_alias,
                display_name=ref.participant_alias,
                scene_nickname=None,
                account_name=None,
                role=ParticipantRole.UNKNOWN,
                is_invoker=ref.is_invoker,
                metadata_status=ParticipantMetadataStatus.UNAVAILABLE,
            )

        snapshot_call = self._bounded_call(
            lambda: _load_current_scene_snapshot(self._session, raw_user_id)
        )
        live_user: User | None = None
        live_member: Member | None = None
        if self._interface is None:
            snapshot = await _safe_lookup(snapshot_call)
        elif is_membership_scene:
            member_scene_type = (
                scene.parent.type
                if scene.is_channel and scene.parent is not None
                else scene.type
            )
            member_scene_id = (
                scene.parent.id
                if scene.is_channel and scene.parent is not None
                else scene.id
            )
            live_member, live_user, snapshot = await asyncio.gather(
                _safe_lookup(
                    self._bounded_call(
                        lambda: self._interface.get_member(
                            member_scene_type,
                            member_scene_id,
                            raw_user_id,
                        )
                    )
                ),
                _safe_lookup(
                    self._bounded_call(lambda: self._interface.get_user(raw_user_id))
                ),
                _safe_lookup(snapshot_call),
            )
        else:
            live_user, snapshot = await asyncio.gather(
                _safe_lookup(
                    self._bounded_call(lambda: self._interface.get_user(raw_user_id))
                ),
                _safe_lookup(snapshot_call),
            )

        if snapshot is None:
            snapshot = _MetadataSnapshot(user=None, member=None)
        observed_user = (
            self._session.user if self._session.user.id == raw_user_id else None
        )
        observed_member = (
            self._session.member
            if self._session.member is not None
            and self._session.member.user.id == raw_user_id
            else None
        )

        member = live_member or snapshot.member or observed_member
        account_user = live_user or (live_member.user if live_member else None)
        account_user = account_user or snapshot.user
        if account_user is None and snapshot.member is not None:
            account_user = snapshot.member.user
        account_user = account_user or observed_user
        if account_user is None and observed_member is not None:
            account_user = observed_member.user

        scene_nickname = _normalize_display_name(
            member.nick if member is not None else None,
            self._config.display_name_chars,
        )
        account_name = _first_display_name(
            account_user,
            self._config.display_name_chars,
        )
        display_name = scene_nickname or account_name or ref.participant_alias
        role = (
            _normalize_role(member) if is_membership_scene else ParticipantRole.UNKNOWN
        )

        has_fallback_display = bool(
            _normalize_display_name(
                snapshot.member.nick if snapshot.member is not None else None,
                self._config.display_name_chars,
            )
            or _first_display_name(snapshot.user, self._config.display_name_chars)
            or _first_display_name(
                snapshot.member.user if snapshot.member is not None else None,
                self._config.display_name_chars,
            )
            or _normalize_display_name(
                observed_member.nick if observed_member is not None else None,
                self._config.display_name_chars,
            )
            or _first_display_name(observed_user, self._config.display_name_chars)
            or _first_display_name(
                observed_member.user if observed_member is not None else None,
                self._config.display_name_chars,
            )
        )
        if is_membership_scene:
            live_member_display = bool(
                _normalize_display_name(
                    live_member.nick if live_member is not None else None,
                    self._config.display_name_chars,
                )
                or _first_display_name(
                    live_member.user if live_member is not None else None,
                    self._config.display_name_chars,
                )
            )
            live_user_display = bool(
                _first_display_name(live_user, self._config.display_name_chars)
            )
            if live_member_display and live_user_display:
                metadata_status = ParticipantMetadataStatus.FULL
            elif live_member_display or live_user_display or has_fallback_display:
                metadata_status = ParticipantMetadataStatus.PARTIAL
            else:
                metadata_status = ParticipantMetadataStatus.UNAVAILABLE
        else:
            if _first_display_name(live_user, self._config.display_name_chars):
                metadata_status = ParticipantMetadataStatus.FULL
            elif has_fallback_display:
                metadata_status = ParticipantMetadataStatus.PARTIAL
            else:
                metadata_status = ParticipantMetadataStatus.UNAVAILABLE

        return ParticipantInfo(
            participant_alias=ref.participant_alias,
            display_name=display_name,
            scene_nickname=scene_nickname,
            account_name=account_name,
            role=role,
            is_invoker=ref.is_invoker,
            metadata_status=metadata_status,
        )

    async def _bounded_call[T](self, call: Callable[[], Awaitable[T]]) -> T:
        async with self._lookup_semaphore:
            return await call()


async def _safe_lookup[T](awaitable: Awaitable[T]) -> T | None:
    try:
        return await awaitable
    except Exception:
        return None


async def _load_current_scene_snapshot(
    session: Session,
    raw_user_id: str,
) -> _MetadataSnapshot:
    statement = (
        select(UserModel.user_data, SessionModel.member_data)
        .join(SessionModel, SessionModel.user_persist_id == UserModel.id)
        .join(BotModel, BotModel.id == SessionModel.bot_persist_id)
        .join(SceneModel, SceneModel.id == SessionModel.scene_persist_id)
        .where(BotModel.self_id == session.self_id)
        .where(BotModel.adapter == _enum_value(session.adapter))
        .where(BotModel.scope == _enum_value(session.scope))
        .where(SceneModel.scene_id == session.scene.id)
        .where(SceneModel.scene_type == session.scene.type.value)
        .where(UserModel.user_id == raw_user_id)
        .limit(1)
    )
    async with get_session() as database:
        row = (await database.execute(statement)).one_or_none()
    if row is None:
        return _MetadataSnapshot(user=None, member=None)

    user_data, member_data = row.tuple()
    user: User | None = None
    member: Member | None = None
    if isinstance(user_data, dict):
        try:
            user = User(**{**user_data, "id": raw_user_id})
        except Exception:
            user = None
    if isinstance(member_data, dict):
        try:
            member = Member.load(member_data)
        except Exception:
            member = None
    return _MetadataSnapshot(user=user, member=member)


def _enum_value(value: str | Enum) -> str:
    return str(value.value) if isinstance(value, Enum) else value


def _normalize_display_name(value: str | None, maximum: int) -> str | None:
    if value is None:
        return None
    normalized = unicodedata.normalize("NFKC", str(value))
    characters: list[str] = []
    for character in normalized:
        if character.isspace():
            characters.append(" ")
            continue
        category = unicodedata.category(character)
        if category in {"Cc", "Cf", "Cs"}:
            continue
        if unicodedata.bidirectional(character) in _BIDI_CONTROL_CLASSES:
            continue
        characters.append(character)
    result = " ".join("".join(characters).split())[:maximum].strip()
    return result or None


def _first_display_name(user: User | None, maximum: int) -> str | None:
    if user is None:
        return None
    return _normalize_display_name(user.nick, maximum) or _normalize_display_name(
        user.name,
        maximum,
    )


def _normalize_role(member: Member | None) -> ParticipantRole:
    if member is None:
        return ParticipantRole.UNKNOWN
    role = member.role
    if role is None:
        return ParticipantRole.MEMBER
    role_id = role.id.casefold()
    if role_id in {"owner", "creator"} or role.level in {100, 640}:
        return ParticipantRole.OWNER
    if role_id in {
        "admin",
        "administrator",
        "channel_admin",
        "channel_administrator",
    } or role.level in {8, 9, 10}:
        return ParticipantRole.ADMIN
    if role_id == "member" or role.level == 1:
        return ParticipantRole.MEMBER
    return ParticipantRole.MEMBER


async def _handle_participant_info(
    context: ZssmToolContext,
    arguments: ParticipantInfoArgs,
) -> ToolOutput:
    try:
        participants = await context.participant_resolver.resolve_known(
            arguments.participant_aliases
        )
    except Exception:
        participants = ()
    participant_values: list[JSONValue] = []
    for participant in participants:
        participant_value: dict[str, JSONValue] = {
            "participant_alias": participant.participant_alias,
            "display_name": participant.display_name,
            "scene_nickname": participant.scene_nickname,
            "account_name": participant.account_name,
            "role": participant.role.value,
            "is_invoker": participant.is_invoker,
            "metadata_status": participant.metadata_status.value,
        }
        participant_values.append(participant_value)
    value: dict[str, JSONValue] = {
        "participants": participant_values,
        "returned": len(participants),
    }
    return ToolOutput(value=value, summary=f"returned={len(participants)}")


def build_participant_info_tool(
    context: ZssmToolContext,
) -> BoundTool[ZssmToolContext, ParticipantInfoArgs]:
    return BoundTool(
        name="get_participant_info",
        description=(
            "Resolve opaque participant aliases to safe display metadata for this "
            "conversation. Unknown aliases return unavailable metadata."
        ),
        arguments_type=bind_participant_info_args(context.participants_config),
        context=context,
        handler=_handle_participant_info,
    )


__all__ = ["InvocationParticipantResolver", "build_participant_info_tool"]
