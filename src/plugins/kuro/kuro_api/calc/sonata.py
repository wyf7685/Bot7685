from typing import TypedDict, override

from pydantic import BaseModel

from ..const import DATA_PATH

SONATA_PATH = DATA_PATH / "sonata"
SONATA_NAMES = {path.name.removesuffix(".json") for path in SONATA_PATH.glob("*.json")}
SONATA_CACHE: dict[str, "WavesSonata"] = {}


class WavesSonataSetDesc(BaseModel):
    desc: str
    param: list[str]


class WavesSonataSetDescWithEffect(WavesSonataSetDesc):
    effect: str


WavesSonataSet = TypedDict(
    "WavesSonataSet",
    {"2": WavesSonataSetDescWithEffect, "5": WavesSonataSetDesc},
)


class WavesSonata(BaseModel):
    name: str
    set: WavesSonataSet

    @override
    def __hash__(self) -> int:
        return hash(self.name)


def get_sonata_detail(sonata_name: str | None) -> WavesSonata | None:
    if sonata_name is None or sonata_name not in SONATA_NAMES:
        return None

    if sonata_name not in SONATA_CACHE:
        path = SONATA_PATH / f"{sonata_name}.json"
        sonata = WavesSonata.model_validate_json(path.read_text(encoding="utf-8"))
        SONATA_CACHE[sonata_name] = sonata

    return SONATA_CACHE[sonata_name]
