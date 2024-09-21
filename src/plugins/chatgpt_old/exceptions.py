# ruff: noqa

class Error(Exception):
    def __init__(self, ErrorInfo):
        self.ErrorInfo = ErrorInfo

    def __str__(self) -> str:
        return self.ErrorInfo


class OverMaxTokenLengthError(Error):
    pass


class NoResponseError(Error):
    pass


class NeedCreateSession(Error):
    pass


class ApiKeyError(Error):
    pass


class NoApiKeyError(Error):
    pass
