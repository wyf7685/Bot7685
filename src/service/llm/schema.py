from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class UserMessage:
    content: str


@dataclass(frozen=True, slots=True)
class SystemMessage:
    content: str


@dataclass(frozen=True, slots=True)
class AssistantMessage:
    content: str


type Message = UserMessage | SystemMessage | AssistantMessage


def dump_messages(*messages: Message) -> list[dict[str, str]]:
    """将类型化的消息转换为 OpenAI API 格式。

    Returns:
        list[dict[str, str]]: 每个元素为
                            {"role": "user"|"system"|"assistant", "content": "..."}
    """
    result: list[dict[str, str]] = []
    for msg in messages:
        if isinstance(msg, SystemMessage):
            result.append({"role": "system", "content": msg.content})
        elif isinstance(msg, UserMessage):
            result.append({"role": "user", "content": msg.content})
        elif isinstance(msg, AssistantMessage):
            result.append({"role": "assistant", "content": msg.content})
    return result


@dataclass(frozen=True, slots=True)
class TokenUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0

    def __add__(self, other: TokenUsage) -> TokenUsage:
        return TokenUsage(
            prompt_tokens=self.prompt_tokens + other.prompt_tokens,
            completion_tokens=self.completion_tokens + other.completion_tokens,
            total_tokens=self.total_tokens + other.total_tokens,
        )

    __iadd__ = __add__
