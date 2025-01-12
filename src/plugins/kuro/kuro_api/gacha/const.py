from .model import CardPoolType

CARD_POOL_NAME: dict[CardPoolType, str] = {
    CardPoolType.CHARACTER: "角色活动唤取",
    CardPoolType.WEAPON: "武器活动唤取",
    CardPoolType.CHARACTER_PERMANENT: "角色常驻唤取",
    CardPoolType.WEAPON_PERMANENT: "武器常驻唤取",
    CardPoolType.BEGINNER: "新手唤取",
    CardPoolType.BEGINNER_SELECT: "新手自选唤取",
    CardPoolType.BEGINNER_SELECT_THANKSGIVING: "新手自选唤取（感恩定向唤取）",
}


GACHA_HEADERS = {
    "accept": "application/json, text/plain, */*",
    "accept-language": "zh-Hans",
    "content-type": "application/json",
    "origin": "https://aki-gm-resources.aki-game.com",
    "referer": "https://aki-gm-resources.aki-game.com/",
    "user-agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
        " AppleWebKit/537.36 (KHTML, like Gecko)"
        " Chrome/131.0.0.0 Safari/537.36"
    ),
}

GACHA_QUERY_URL = {
    "https://aki-gm-resources.aki-game.com": "https://gmserver-api.aki-game2.com",
    "https://aki-gm-resources-oversea.aki-game.net": "https://gmserver-api.aki-game2.net",
}
