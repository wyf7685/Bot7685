import contextlib
import functools
import re
import shutil
import uuid
from collections.abc import AsyncIterator
from pathlib import Path
from string import Formatter
from typing import Annotated, Any, NamedTuple, Self

import anyio
import anyio.to_thread
from nonebot.params import Depends
from nonebot_plugin_localstore import get_plugin_cache_dir
from nonebot_plugin_orm import AsyncSession, Model, get_session
from pydantic import BaseModel, field_validator, model_validator
from sqlalchemy import Boolean, Integer, String, Text, UniqueConstraint, func, select
from sqlalchemy.orm import Mapped, mapped_column

from src.utils import attach_async_context

CACHE_DIR = get_plugin_cache_dir()


class Repos(NamedTuple):
    owner: str
    repo: str


class DownloadedArtifact(NamedTuple):
    name: str
    path: Path
    artifact_id: int


WorkflowID = int | str


_TEMPLATE_ROOTS = {
    "name",
    "run",
    "head_sha",
    "head_sha_short",
    "artifact",
    "match",
}
_FORMATTER = Formatter()


class ArtifactConfig(BaseModel):
    filter_regex: str | None = None
    rename_template: str | None = None

    @field_validator("filter_regex")
    @classmethod
    def validate_filter_regex(cls, value: str | None) -> str | None:
        if value is not None:
            try:
                re.compile(value)
            except re.error as exc:
                raise ValueError(
                    "filter_regex must be a valid regular expression"
                ) from exc
        return value

    @field_validator("rename_template")
    @classmethod
    def validate_rename_template(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not value.strip():
            raise ValueError("rename_template must not be empty")
        try:
            fields = _FORMATTER.parse(value)
            for _, field_name, _, _ in fields:
                if field_name is None:
                    continue
                if not field_name:
                    raise ValueError("rename_template must use named fields")
                root = field_name.split(".", 1)[0].split("[", 1)[0]
                if root not in _TEMPLATE_ROOTS and not re.fullmatch(r"\$\d+", root):
                    raise ValueError(f"unsupported rename_template field: {root}")
        except ValueError as exc:
            raise ValueError(f"invalid rename_template: {exc}") from exc
        return value

    @model_validator(mode="after")
    def validate_match_references(self) -> Self:
        if self.rename_template is None:
            return self
        pattern = (
            re.compile(self.filter_regex) if self.filter_regex is not None else None
        )
        group_count = pattern.groups if pattern is not None else 0
        group_names = pattern.groupindex if pattern is not None else {}
        for _, field_name, _, _ in _FORMATTER.parse(self.rename_template):
            if field_name is None:
                continue
            root = field_name.split(".", 1)[0].split("[", 1)[0]
            if root == "match" and field_name != "match":
                if pattern is None:
                    raise ValueError(
                        "rename_template references match without filter_regex"
                    )
                if field_name.startswith("match["):
                    item = re.match(r"match\[([^\]]+)\]", field_name)
                    if item is None:
                        raise ValueError(
                            f"invalid match reference in rename_template: {field_name}"
                        )
                    group = item.group(1)
                    if re.fullmatch(r"[0-9]+", group):
                        group_index = int(group)
                        available = group_index <= group_count
                    else:
                        available = group in group_names
                    if not available:
                        raise ValueError(
                            "rename_template references unavailable match "
                            f"capture group: {field_name}"
                        )
                continue
            if not (match := re.fullmatch(r"\$(\d+)", root)):
                continue
            group_index = int(match.group(1))
            if pattern is None or (group_index > group_count and group_index != 0):
                raise ValueError(
                    f"rename_template references unavailable capture group: {root}"
                )
        return self

    def match_regex(self, name: str) -> re.Match[str] | None:
        if self.filter_regex is None:
            return None
        return re.search(self.filter_regex, name)

    def rename(self, artifact_name: str, format_data: dict[str, Any]) -> str:
        if self.rename_template is None:
            return artifact_name
        return self.rename_template.format(name=artifact_name, **format_data)


class Subscription(Model):
    __table_args__ = (
        UniqueConstraint(
            "scene_persist_id",
            "owner",
            "repo",
            "workflow_kind",
            "workflow_value",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_persist_id: Mapped[int] = mapped_column(Integer, nullable=False)
    scene_persist_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    owner: Mapped[str] = mapped_column(String(255), nullable=False)
    repo: Mapped[str] = mapped_column(String(255), nullable=False)
    workflow_kind: Mapped[int] = mapped_column(Integer, nullable=False)
    workflow_value: Mapped[str] = mapped_column(String(255), nullable=False)
    upload_artifacts: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    filter_regex: Mapped[str | None] = mapped_column(Text)
    rename_template: Mapped[str | None] = mapped_column(Text)

    @classmethod
    def create(
        cls,
        *,
        session_persist_id: int,
        scene_persist_id: int,
        owner: str,
        repo: str,
        workflow_id: WorkflowID | None,
    ) -> Self:
        workflow_kind, workflow_value = _dump_workflow_id(workflow_id)
        return cls(
            session_persist_id=session_persist_id,
            scene_persist_id=scene_persist_id,
            owner=owner,
            repo=repo,
            workflow_kind=workflow_kind,
            workflow_value=workflow_value,
        )

    @property
    def repos(self) -> Repos:
        return Repos(owner=self.owner, repo=self.repo)

    @property
    def workflow_id(self) -> WorkflowID | None:
        match self.workflow_kind:
            case 0:
                return None
            case 1:
                return int(self.workflow_value)
            case 2:
                return self.workflow_value
            case value:
                raise ValueError(f"unsupported workflow kind: {value}")

    @property
    def artifact_upload_config(self) -> ArtifactConfig | None:
        if not self.upload_artifacts:
            return None
        return ArtifactConfig(
            filter_regex=self.filter_regex,
            rename_template=self.rename_template,
        )

    @artifact_upload_config.setter
    def artifact_upload_config(self, value: ArtifactConfig | None) -> None:
        self.upload_artifacts = value is not None
        self.filter_regex = value.filter_regex if value is not None else None
        self.rename_template = value.rename_template if value is not None else None


def _dump_workflow_id(workflow_id: WorkflowID | None) -> tuple[int, str]:
    match workflow_id:
        case None:
            return 0, ""
        case int() as value:
            return 1, str(value)
        case str() as value:
            return 2, value


def _subscription_identity(sub: Subscription) -> tuple[int, str]:
    return sub.workflow_kind, sub.workflow_value


@attach_async_context(get_session)
async def list_subscriptions(
    session: AsyncSession,
    *,
    scene_persist_id: int | None = None,
    repos: Repos | None = None,
) -> list[Subscription]:
    statement = select(Subscription).order_by(Subscription.id)
    if scene_persist_id is not None:
        statement = statement.where(Subscription.scene_persist_id == scene_persist_id)
    if repos is not None:
        statement = statement.where(
            Subscription.owner == repos.owner,
            Subscription.repo == repos.repo,
        )
    return list((await session.scalars(statement)).all())


@attach_async_context(get_session)
async def subscription_exists(
    session: AsyncSession,
    sub: Subscription,
) -> bool:
    workflow_kind, workflow_value = _subscription_identity(sub)
    statement = select(Subscription.id).where(
        Subscription.scene_persist_id == sub.scene_persist_id,
        Subscription.owner == sub.owner,
        Subscription.repo == sub.repo,
        Subscription.workflow_kind == workflow_kind,
        Subscription.workflow_value == workflow_value,
    )
    return await session.scalar(statement) is not None


@attach_async_context(get_session)
async def add_subscription(
    session: AsyncSession,
    sub: Subscription,
) -> None:
    session.add(sub)
    await session.commit()
    await session.refresh(sub)


@attach_async_context(get_session)
async def remove_subscription(
    session: AsyncSession,
    sub: Subscription,
) -> bool:
    workflow_kind, workflow_value = _subscription_identity(sub)
    statement = select(Subscription).where(
        Subscription.scene_persist_id == sub.scene_persist_id,
        Subscription.owner == sub.owner,
        Subscription.repo == sub.repo,
        Subscription.workflow_kind == workflow_kind,
        Subscription.workflow_value == workflow_value,
    )
    existing = await session.scalar(statement)
    if existing is None:
        return False
    await session.delete(existing)
    await session.commit()
    return True


@attach_async_context(get_session)
async def count_subscriptions(session: AsyncSession) -> int:
    return int(await session.scalar(select(func.count(Subscription.id))) or 0)


async def _get_cache_directory() -> AsyncIterator[Path]:
    cache_dir = CACHE_DIR / uuid.uuid4().hex
    cache_dir.mkdir(parents=True, exist_ok=True)
    try:
        yield cache_dir
    finally:
        await anyio.to_thread.run_sync(
            functools.partial(shutil.rmtree, cache_dir, ignore_errors=True)
        )


get_cache_directory = contextlib.asynccontextmanager(_get_cache_directory)


CacheDirectory = Annotated[Path, Depends(_get_cache_directory)]
