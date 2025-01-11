from enum import Enum
from typing import Literal


class GameId(int, Enum):
    PNS = 2
    WUWA = 3


type PnsGameId = Literal[GameId.PNS]
type WuwaGameId = Literal[GameId.WUWA]
