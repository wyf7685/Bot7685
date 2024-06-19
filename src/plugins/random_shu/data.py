import json
from pathlib import Path
from random import Random
from typing import Self

from pydantic import BaseModel

from .constant import data_fp, image_dir

random = Random()


class Data(BaseModel):
    name: str
    text: str
    weight: int

    @classmethod
    def _load(cls) -> list[Self]:
        return [
            cls.model_validate(i)
            for i in json.loads(data_fp.read_text(encoding="utf-8"))
        ]

    @classmethod
    def _save(cls, data: list[Self]) -> None:
        data_fp.write_text(
            data=json.dumps(
                [i.model_dump() for i in data],
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    @classmethod
    def choose(cls) -> Self:
        data = cls._load()
        total = sum(i.weight for i in data)
        key = random.randint(0, total)
        for item in data:
            if item.weight > key:
                return item
            key -= item.weight
        else:
            return data[-1]

    @classmethod
    def find(cls, name: str) -> Self | None:
        data = cls._load()
        for item in data:
            if item.name == name:
                return item

    def add_weight(self, w: int) -> None:
        self.weight = max(self.weight + w, 10)
        data = self._load()
        next(i for i in data if i.name == self.name).weight = self.weight
        self._save(data)

    @property
    def path(self) -> Path:
        return image_dir / self.name
