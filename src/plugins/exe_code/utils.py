from typing import ClassVar, Dict, Self


class Buffer:
    _user_buf: ClassVar[Dict[str, Self]] = {}
    _buffer: str

    def __new__(cls, uin: str) -> Self:
        if uin not in cls._user_buf:
            buf = super(Buffer, cls).__new__(cls)
            buf._buffer = ""
            cls._user_buf[uin] = buf
        return cls._user_buf[uin]

    def write(self, text: str) -> None:
        assert isinstance(text, str)
        self._buffer += text

    def getvalue(self) -> str:
        value, self._buffer = self._buffer, ""
        return value
