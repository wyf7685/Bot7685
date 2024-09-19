import random
from collections import UserList, UserString


class APIKey(UserString):
    def __init__(self, key: str):
        super().__init__(key.strip())
        self.status: bool = True
        self.fail_reason: str = ""

    @property
    def key(self) -> str:
        return self.data

    def show(self) -> str:
        return f"[{self.data[:8]}....{self.data[-4:]}]"

    def fail(self, reason: str):
        self.status = False
        self.fail_reason = reason

    def show_fail(self) -> str:
        return f"{self.show()} {self.fail_reason}"


class APIKeyPool(UserList):
    def __init__(self, api_keys: str | list):
        if not api_keys or not (isinstance(api_keys, str | list)):
            raise Exception("请输入正确的 API KEY")
        if isinstance(api_keys, str):
            api_keys = [api_keys]
        self.valid_num: int = len(api_keys)
        super().__init__(map(APIKey, api_keys))

    @property
    def api_keys(self) -> list[APIKey]:
        return self.data

    def __len__(self):
        return len(self.api_keys)

    @property
    def len(self) -> int:
        return len(self.api_keys)

    def shuffle(self):
        random.shuffle(self.api_keys)

    def fail_keys(self) -> list[APIKey]:
        return [k for k in self.api_keys if not k.status]

    def show_fail_keys(self) -> str:
        failed = [k.show_fail() for k in self.fail_keys()]
        fail_num = len(failed)
        self.valid_num = len(self.api_keys) - fail_num
        return (
            f"当前存在APIkey共 {len(self.api_keys)} 个\n"
            + f"已失效key共 {fail_num} 个：\n"
            + "\n".join(failed)
        )
