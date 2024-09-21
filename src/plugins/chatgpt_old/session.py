# ruff: noqa

import copy
import json
from datetime import datetime
from pathlib import Path
from typing import Optional

import httpx
from nonebot.adapters.onebot.v11 import GroupMessageEvent, MessageEvent
from nonebot.log import logger
from openai import (
    APIResponseValidationError,
    AsyncOpenAI,
    AuthenticationError,
    RateLimitError,
)
from openai.types.chat import ChatCompletion

from .apikey import APIKey, APIKeyPool
from .config import plugin_config
from .exceptions import NeedCreateSession, NoResponseError
from .preset import templateDict

type_user_id = int | str
type_group_id = str
PRIVATE_GROUP: str = "Private"

proxy: str | None = plugin_config.openai_proxy
if proxy:
    proxy_client = httpx.AsyncClient(proxies=proxy)
    logger.debug("已配置代理")
else:
    proxy_client = httpx.AsyncClient()
    logger.warning("未配置代理")


def get_group_id(event: MessageEvent) -> str:
    if isinstance(event, GroupMessageEvent):  # 当在群聊中时
        return str(event.group_id)
    else:  # 当在私聊中时
        return f"{PRIVATE_GROUP}_{event.get_user_id()}"


class SessionContainer:
    def __init__(self) -> None:
        self.api_keys: APIKeyPool = plugin_config.api_key_pool
        self.base_url: str = plugin_config.openai_api_base
        self.chat_memory_max: int = min(plugin_config.chat_memory_max, 2)
        self.history_max: int = 100
        self.dir_path: Path = plugin_config.history_save_path
        self.sessions: list[Session] = []
        self.session_usage: dict[type_group_id, dict[type_user_id, Session]] = {}
        self.default_only_admin: bool = plugin_config.default_only_admin
        self.group_auth: dict[str, bool] = {}

        if not self.dir_path.exists():
            self.dir_path.mkdir(parents=True)
        if plugin_config.history_max > self.chat_memory_max:
            self.history_max = plugin_config.history_max

        self.load()
        self.load_group_auth()

    @property
    def group_auth_file_path(self) -> Path:
        return self.dir_path / "group_auth_file.json"

    def save_group_auth(self) -> None:
        with open(self.group_auth_file_path, "w", encoding="utf8") as f:
            json.dump(self.group_auth, f, ensure_ascii=False)

    def load_group_auth(self) -> None:
        if not self.group_auth_file_path.exists():
            self.save_group_auth()
            return
        with open(self.group_auth_file_path, encoding="utf8") as f:
            self.group_auth = json.load(f)

    def get_group_auth(self, gid: str) -> bool:
        return self.group_auth.setdefault(gid, self.default_only_admin)

    def set_group_auth(self, gid: str, auth: bool) -> None:
        self.group_auth[gid] = auth
        self.save_group_auth()

    async def delete_session(self, session: "Session", gid: str) -> None:
        group_usage: dict[type_user_id, Session] = self.get_group_usage(gid)
        users = {uid for uid, s in group_usage.items() if s is session}
        for user in users:
            group_usage.pop(user, None)
        self.sessions.remove(session)
        session.delete_file()
        logger.success(f"成功删除群 {gid} 会话 {session.name}")

    def get_group_sessions(self, group_id: str | int) -> list["Session"]:
        return [s for s in self.sessions if s.group == str(group_id)]

    @staticmethod
    def old_version_check(session: "Session") -> None:
        if session.group == PRIVATE_GROUP:
            session.file_path.unlink(missing_ok=True)
            session.group = PRIVATE_GROUP + f"_{session.creator}"
            session.save()

    def load(self) -> None:
        files: list[Path] = list(self.dir_path.glob("*.json"))
        try:
            files.remove(self.group_auth_file_path)
        except ValueError:
            pass
        for file in files:
            session = Session.reload_from_file(file)
            if not session:
                continue
            self.old_version_check(session)
            self.sessions.append(session)
            group = self.get_group_usage(session.group)
            for user in session.users:
                group[user] = session

    def get_group_usage(self, gid: str | int) -> dict[type_user_id, "Session"]:
        return self.session_usage.setdefault(str(gid), {})

    def get_user_usage(self, gid: str | int, uid: int) -> "Session":
        try:
            return self.get_group_usage(gid)[uid]
        except KeyError:
            raise NeedCreateSession(f"群{gid} 用户{uid} 需要创建 Session")

    def create_with_chat_log(
        self,
        chat_log: list[dict[str, str]],
        creator: int | str,
        group: int | str,
        name: str = "",
    ) -> "Session":
        session = Session(
            chat_log=chat_log,
            creator=creator,
            group=group,
            dir_path=self.dir_path,
            name=name,
            history_max=self.history_max,
            chat_memory_max=self.chat_memory_max,
        )
        self.get_group_usage(group)[creator] = session
        self.sessions.append(session)
        session.add_user(creator)
        logger.success(f"{creator} 成功创建会话 {session.name}")
        return session

    def create_with_template(
        self, template_id: str, creator: int | str, group: int | str
    ) -> "Session":
        deep_copy = copy.deepcopy(templateDict[template_id].preset)
        return self.create_with_chat_log(
            deep_copy, creator, group, name=templateDict[template_id].name
        )

    def create_with_str(
        self, custom_prompt: str, creator: int | str, group: int | str, name: str = ""
    ) -> "Session":
        prompt = [
            {"role": "user", "content": custom_prompt},
            {"role": "assistant", "content": "好"},
        ]
        return self.create_with_chat_log(prompt, creator, group, name=name)

    def create_with_session(
        self, session: "Session", creator: int, group: str
    ) -> "Session":
        new_session: Session = Session(
            chat_log=session.chat_memory,
            creator=creator,
            group=group,
            name=session.name,
            dir_path=self.dir_path,
            history_max=self.history_max,
            chat_memory_max=self.chat_memory_max,
        )
        self.get_group_usage(group)[creator] = new_session
        self.sessions.append(new_session)
        new_session.add_user(creator)
        logger.success(f"{creator} 成功创建会话 {new_session.name}")
        return new_session


class Session:
    def __init__(
        self,
        chat_log: list[dict[str, str]],
        creator: int | str,
        group: int | str,
        name: str,
        chat_memory_max: int,
        dir_path: Path,
        history_max: int = 100,
        users=None,
        is_save: bool = True,
        basic_len: int | None = None,
    ) -> None:
        self.history: list[dict[str, str]] = chat_log
        self.creator: str = str(creator)
        self._users: set[type_user_id] = set(users) if users else set()
        self.group: str = str(group)
        self.name: str = name
        self.chat_memory_max: int = chat_memory_max
        self.history_max: int = history_max
        self.creation_time: int = int(datetime.now().timestamp())
        self.dir_path: Path = dir_path
        if basic_len is not None:
            self.basic_len: int = basic_len
        else:
            self.basic_len = len(self.history)
        if is_save:
            self.save()

    @property
    def prompt(self) -> str:
        return self.history[0].get("content", "").strip()

    def rename(self, name: str) -> None:
        self.file_path.unlink(missing_ok=True)
        self.name = name
        self.save()

    @property
    def users(self) -> set[type_user_id]:
        return self._users

    def add_user(self, user: type_user_id) -> None:
        self._users.add(user)
        self.save()

    def del_user(self, user: int) -> None:
        self._users.discard(user)
        self.save()

    def delete_file(self):
        self.file_path.unlink(missing_ok=True)

    @property
    def chat_memory(self) -> list[dict[str, str]]:
        return (
            self.history[: self.basic_len]
            + self.history[self.basic_len - self.chat_memory_max :]
        )

    @property
    def creation_datetime(self) -> datetime:
        return datetime.fromtimestamp(self.creation_time)

    async def ask_with_content(
        self,
        api_keys: APIKeyPool,
        base_url: str,
        content: str,
        role: str = "user",
        temperature: float = 0.5,
        model: str = "gpt-3.5-turbo",
        max_tokens=1024,
    ) -> str:
        self.update(content, role)
        return await self.ask(api_keys, base_url, temperature, model, max_tokens)

    async def ask(
        self,
        api_keys: APIKeyPool,
        base_url: str,
        temperature: float = 0.5,
        model: str = "gpt-3.5-turbo",
        max_tokens=1024,
    ) -> str:
        if api_keys.valid_num <= 0:
            logger.error("当前不存在api key，请在配置文件里进行配置...")
            return "当前不存在可用apikey，请联系管理员检查apikey信息"
        if plugin_config.key_load_balancing:
            api_keys.shuffle()
        for num, api_key in enumerate(api_keys):
            api_key: APIKey
            log_info = f"Api Key([{num + 1}/{len(api_keys)}]): {api_key.show()}"
            if not api_key.status:
                logger.warning(
                    f"{log_info} 被标记失效，已跳过... \n失效原因:{api_key.fail_reason}"
                )
                continue
            aclient = AsyncOpenAI(
                api_key=api_key.key, base_url=base_url, http_client=proxy_client
            )
            logger.debug(f"当前使用 {log_info}")
            try:
                completion = await aclient.chat.completions.create(
                    model=model,
                    messages=self.chat_memory,  # type: ignore
                    temperature=temperature,
                    max_tokens=max_tokens,
                    timeout=min(10, plugin_config.timeout),
                )
                # 不知道新版本这个改成什么了
                if completion.choices is None:
                    raise NoResponseError("未返回任何choices")
                if len(completion.choices) == 0:
                    raise NoResponseError("返回的choices长度为0")
                if completion.choices[0].message is None:
                    raise NoResponseError("未返回任何文本!")

                self.update_from_completion(completion)
                logger.debug(f"{log_info} 请求成功")
                return completion.choices[0].message.content or ""
            except RateLimitError as e:
                if "You exceeded your current quota" in getattr(e, "user_message", ""):
                    logger.warning(f"{log_info} 额度耗尽，已失效，尝试使用下一个...")
                    logger.warning(f"{type(e)}: {e}")
                    api_key.fail(f"{type(e).__name__}: {e}")
                    api_keys.valid_num -= 1
                else:
                    logger.warning(f"{log_info} 请求速率过快，尝试使用下一个...")
                    logger.warning(f"{e}")
            except (
                APIResponseValidationError,
                AuthenticationError,
                PermissionError,
            ) as e:
                logger.warning(f"{log_info} 格式或权限错误，已失效，尝试使用下一个...")
                logger.warning(f"{e}")
                api_key.fail(f"{type(e).__name__}: {e}")
                api_keys.valid_num -= 1
            except Exception as e:
                logger.warning(f"{log_info} 请求出现其他错误，尝试使用下一个...")
                logger.warning(f"{type(e)}: {e}")
        return "请求失败...请联系管理员查看错误日志和apikey信息"

    def update(self, content: str, role: str = "user") -> None:
        self.history.append({"role": role, "content": content})
        while len(self.history) > self.history_max:
            self.history.pop(0)
        self.save()

    def update_from_completion(self, completion: ChatCompletion) -> None:
        role = completion.choices[0].message.role
        content = completion.choices[0].message.content or ""
        self.update(content, role)

    @classmethod
    def reload(
        cls,
        chat_log: list[dict[str, str]],
        creator: int,
        group: str,
        name: str,
        creation_time: int,
        chat_memory_max: int,
        dir_path: Path,
        history_max: int,
        users: list[int] | None = None,
        basic_len: int | None = None,
    ) -> "Session":
        session: Session = cls(
            chat_log,
            creator,
            group,
            name,
            chat_memory_max,
            dir_path,
            history_max,
            users,
            False,
            basic_len,
        )
        session.creation_time = creation_time
        return session

    @classmethod
    def reload_from_file(cls, file_path: Path) -> Optional["Session"]:
        try:
            with file_path.open(encoding="utf-8") as f:
                session = cls.reload(dir_path=file_path.parent, **json.load(f))
                logger.debug(f"从文件 {file_path} 加载 Session 成功")
                return session
        except Exception as e:
            logger.error(f"从文件 {file_path} 加载 Session 失败: {e!r}")

    def as_dict(self) -> dict:
        return {
            "chat_log": self.history,
            "creator": self.creator,
            "users": list(self._users),
            "group": self.group,
            "name": self.name,
            "creation_time": self.creation_time,
            "chat_memory_max": self.chat_memory_max,
            "history_max": self.history_max,
            "basic_len": self.basic_len,
        }

    @property
    def file_path(self) -> Path:
        file_name = f"{self.group}_{self.name}_{self.creator}_{self.creation_time}.json"
        return self.dir_path / file_name

    def save(self) -> None:
        with self.file_path.open("w+", encoding="utf-8") as f:
            json.dump(self.as_dict(), f, ensure_ascii=False)

    def dump2json_str(self) -> str:
        return json.dumps(self.chat_memory, ensure_ascii=False)


session_container = SessionContainer()
