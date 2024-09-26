from nonebot_plugin_localstore import get_plugin_data_dir

DATA_DIR = get_plugin_data_dir()
DATABASE_URL = f"sqlite+aiosqlite:///{DATA_DIR / 'data.db'}"


URL_TOKEN_PASSWORD = "https://as.hypergryph.com/user/auth/v1/token_by_phone_password"  # noqa: S105
URL_GRANT_CODE = "https://as.hypergryph.com/user/oauth2/v2/grant"
URL_GEN_CRED = "https://zonai.skland.com/api/v1/user/auth/generate_cred_by_code"
URL_SIGN = "https://zonai.skland.com/api/v1/game/attendance"
URL_BINDING = "https://zonai.skland.com/api/v1/game/player/binding"
URL_USER_INFO = "https://zonai.skland.com/api/v1/user/me"
URL_BASIC_INFO = "https://as.hypergryph.com/user/info/v1/basic"
URL_EXCHANGE_CODE = "https://ak.hypergryph.com/user/api/gift/exchange"

USER_AGENT = (
    "Skland/1.0.1 (com.hypergryph.skland; build:100001014; Android 31; ) Okhttp/4.11.0"
)


HEADERS = {
    "cred": "",
    "User-Agent": USER_AGENT,
    "Accept-Encoding": "gzip",
    "Connection": "close",
}

HEADERS_LOGIN = {
    "User-Agent": USER_AGENT,
    "Accept-Encoding": "gzip",
    "Connection": "close",
}

HEADERS_SIGN = {
    "platform": "",
    "timestamp": "",
    "dId": "",
    "vName": "",
}

HEADERS_EXCHANGE_CODE = {
    "Host": "ak.hypergryph.com",
    "Accept": "application/json",
    "Accept-Language": "zh-CN,zh-Hans;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Content-Type": "application/json;charset=utf-8",
    "Origin": "https://ak.hypergryph.com",
    "Referer": "https://ak.hypergryph.com/user/exchangeGift",
    "Connection": "close",
    "Cookie": "csrf_token=U",
    "x-csrf-token": "U",
}
