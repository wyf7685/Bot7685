import contextlib
import functools
import re
import shutil
import uuid
from collections.abc import AsyncIterator
from copy import deepcopy
from pathlib import Path
from string import Formatter
from typing import Annotated, Any, NamedTuple, Self

import anyio
import anyio.to_thread
from nonebot.params import Depends
from nonebot_plugin_alconna import Target
from nonebot_plugin_localstore import get_plugin_cache_dir, get_plugin_data_dir
from pydantic import BaseModel, field_validator, model_validator

from src.utils import ConfigListFile

DATA_DIR = get_plugin_data_dir()
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


class Subscription(BaseModel):
    owner: str
    repo: str
    workflow_id: WorkflowID | None = None
    target_data: dict[str, Any]
    artifact_upload_config: ArtifactConfig | None = None

    @property
    def repos(self) -> Repos:
        return Repos(owner=self.owner, repo=self.repo)

    @property
    def target(self) -> Target:
        return Target.load(deepcopy(self.target_data))

    def verify(self, other: Subscription) -> bool:
        return (
            self.target.verify(other.target)
            and self.repos == other.repos
            and self.workflow_id == other.workflow_id
        )


subscriptions = ConfigListFile(DATA_DIR / "subscriptions.json", Subscription)


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
