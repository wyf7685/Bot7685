from msgspec import json as msgjson

from ..const import DATA_PATH

WUWA_ID2NAME: dict[str, str] = {}


def _get_wuwa_id2name() -> dict[str, str]:
    if not WUWA_ID2NAME:
        path = DATA_PATH / "id2name.json"
        WUWA_ID2NAME.update(msgjson.decode(path.read_text(encoding="utf-8")))
    return WUWA_ID2NAME


def wuwa_find_role_id(name: str) -> int | None:
    for role_id, role_name in _get_wuwa_id2name().items():
        if name in role_name:
            return int(role_id)
    return None
