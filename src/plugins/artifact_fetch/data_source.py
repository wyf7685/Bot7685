import functools
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


class Subscription(BaseModel):
    owner: str
    repo: str
    workflow_id: WorkflowID | None = None
    target_data: dict[str, Any]
    upload_artifact: bool = False
    extra: dict[str, Any] = Field(default_factory=dict)

    @property
    def repos(self) -> Repos:
        return Repos(owner=self.owner, repo=self.repo)

    @property
    def target(self) -> Target:
        return Target.load(self.target_data)


subscriptions = ConfigListFile(DATA_DIR / "subscriptions.json", Subscription)


async def _cache_directory() -> AsyncIterator[anyio.Path]:
    cache_dir = CACHE_DIR / uuid.uuid4().hex
    await cache_dir.mkdir(parents=True, exist_ok=True)
    try:
        yield cache_dir
    finally:
        await anyio.to_thread.run_sync(
            functools.partial(shutil.rmtree, cache_dir, ignore_errors=True)
        )


CacheDirectory = Annotated[anyio.Path, Depends(_cache_directory)]
