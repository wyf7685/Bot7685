from typing import ClassVar, override


class KuroApiException(Exception):
    """库洛 API 错误基类"""

    enable_log: ClassVar[bool] = True

    msg: str

    @override
    def __init__(self, msg: str) -> None:
        super().__init__(msg)
        self.msg = msg


class ApiRequestFailed(KuroApiException):
    """API 请求失败"""


class ApiResponseValidationFailed(KuroApiException):
    """API 返回值验证失败"""

    raw: dict[str, object]

    @override
    def __init__(self, msg: str, raw: dict[str, object]) -> None:
        super().__init__(msg)
        self.raw = raw

        if self.enable_log:
            try:
                from loguru import logger
            except ImportError:
                pass
            else:
                logger.opt(exception=self).warning(f"API 返回值验证失败: {msg} \n{raw}")


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


class GachaApiRequestFailed(ApiRequestFailed, GachaApiException):
    """抽卡 API 请求失败"""


class GachaApiResponseValidationFailed(  # pyright:ignore[reportUnsafeMultipleInheritance]
    ApiResponseValidationFailed,
    GachaApiException,
):
    """抽卡 API 返回值验证失败"""

    @override
    def __init__(self, msg: str, raw: dict[str, object]) -> None:
        ApiResponseValidationFailed.__init__(self, msg, raw)
