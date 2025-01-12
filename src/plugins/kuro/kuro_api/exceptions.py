# ruff: noqa: N818


class KuroApiException(Exception):
    """库洛 API 错误基类"""

    msg: str

    def __init__(self, msg: str) -> None:
        super().__init__(msg)
        self.msg = msg


class ApiRequestFailed(KuroApiException):
    """API 请求失败"""


class ApiCallFailed(KuroApiException):
    """API 调用失败"""


class RoleNotFound(KuroApiException):
    """未找到角色"""


class AlreadySignin(KuroApiException):
    """已签到"""


class GachaApiException(KuroApiException):
    """抽卡 API 错误基类"""


class InvalidGachaUrl(GachaApiException):
    """无效的抽卡 URL"""
