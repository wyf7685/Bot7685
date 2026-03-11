import contextlib
import functools
import re
import shutil
import uuid
from collections.abc import AsyncIterator
from typing import Annotated, Any, NamedTuple

import anyio
import anyio.to_thread
from nonebot.params import Depends
from nonebot_plugin_alconna import Target
from nonebot_plugin_localstore import get_plugin_cache_dir, get_plugin_data_dir
from pydantic import BaseModel, Field

from src.utils import ConfigListFile

DATA_DIR = get_plugin_data_dir()
CACHE_DIR = anyio.Path(get_plugin_cache_dir())


class Repos(NamedTuple):
    owner: str
    repo: str


WorkflowID = int | str


class ArtifactConfig(BaseModel):
    filter_regex: str | None = None
    rename_template: str | None = None
    extra: dict[str, Any] = Field(default_factory=dict)

    def match_regex(self, name: str) -> re.Match[str] | None:
        if self.filter_regex is None:
            return None
        return re.search(self.filter_regex, name)

    def rename(self, artifact_name: str, **kwargs: Any) -> str:
        if self.rename_template is None:
            return artifact_name
        return self.rename_template.format(name=artifact_name, **kwargs)


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
        return Target.load(self.target_data)

    def verify(self, other: Subscription) -> bool:
        return (
            self.target.verify(other.target)
            and self.repos == other.repos
            and self.workflow_id == other.workflow_id
        )


subscriptions = ConfigListFile(DATA_DIR / "subscriptions.json", Subscription)


async def _get_cache_directory() -> AsyncIterator[anyio.Path]:
    cache_dir = CACHE_DIR / uuid.uuid4().hex
    await cache_dir.mkdir(parents=True, exist_ok=True)
    try:
        yield cache_dir
    finally:
        await anyio.to_thread.run_sync(
            functools.partial(shutil.rmtree, cache_dir, ignore_errors=True)
        )


get_cache_directory = contextlib.asynccontextmanager(_get_cache_directory)


CacheDirectory = Annotated[anyio.Path, Depends(_get_cache_directory)]
