import json
from pathlib import Path
from random import Random
from typing import Optional, Self

import aiofiles
from nonebot.compat import model_dump, type_validate_python
from pydantic import BaseModel

from .constant import data_fp, image_dir

random = Random()


class Data(BaseModel):
    name: str
    text: str
    weight: int

    @property
    def path(self) -> Path:
        return image_dir / self.name

    @classmethod
    async def _load(cls) -> list[Self]:
        async with aiofiles.open(data_fp, "r+", encoding="utf-8") as file:
            raw = await file.read()
        return [type_validate_python(cls, i) for i in json.loads(raw)]

    @classmethod
    async def _save(cls, data: list[Self]) -> None:
        raw = json.dumps(
            [model_dump(i) for i in data],
            ensure_ascii=False,
            indent=2,
        )
        async with aiofiles.open(data_fp, "w+", encoding="utf-8") as file:
            await file.write(raw)

    @classmethod
    async def choose(cls) -> Self:
        data = await cls._load()
        total = sum(max(10, i.weight) for i in data)
        key = random.randint(0, total)
        for item in data:
            if item.weight > key:
                return item
            key -= item.weight
        else:
            return data[-1]

    @classmethod
    async def find(cls, name: str) -> Optional[Self]:
        data = await cls._load()
        for item in data:
            if item.name == name:
                return item

    async def add_weight(self, w: int) -> None:
        self.weight = max(self.weight + w, 10)
        data = await self._load()
        next(i for i in data if i.name == self.name).weight = self.weight
        await self._save(data)
