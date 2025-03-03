from .const import VERSION
from .utils import lazy_import

__version__ = VERSION

lazy_import(
    {
        "KuroApi": "api",
        "GameId": "const",
        "KuroApiException": "exceptions",
        "WuwaGachaApi": "gacha",
        "WuwaCalc": "calc",
    }
)
