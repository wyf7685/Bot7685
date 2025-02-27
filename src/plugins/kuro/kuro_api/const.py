from enum import Enum
from pathlib import Path
from typing import Literal

APP_NAME = "wyf7685/kuro-api"
VERSION = "0.1.0"


class GameId(int, Enum):
    PNS = 2
    WUWA = 3


type PnsGameId = Literal[GameId.PNS]
type WuwaGameId = Literal[GameId.WUWA]

DATA_PATH = Path(__file__).parent / "data"
