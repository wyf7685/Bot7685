import dataclasses
from typing import Any, Self


@dataclasses.dataclass(frozen=True, slots=True)
class ContentPartText:
    text: str


@dataclasses.dataclass(frozen=True, slots=True)
class ContentPartImage:
    url: str


@dataclasses.dataclass(frozen=True, slots=True)
class BaseMessage:
    content: str | list[ContentPartText | ContentPartImage]

    def dump_content(self) -> str | list[dict[str, Any]]:
        if isinstance(self.content, str):
            return self.content

        result: list[dict[str, Any]] = []
        for part in self.content:
            match part:
                case ContentPartText(text=text):
                    result.append({"type": "text", "text": text})
                case ContentPartImage(url=url):
                    result.append({"type": "image_url", "image_url": {"url": url}})
        return result

    @classmethod
    def text(cls, text: str) -> Self:
        return cls(content=text)

    @classmethod
    def image(cls, url: str) -> Self:
        return cls(content=[ContentPartImage(url=url)])

    def __add__(self, other: Self) -> Self:
        if type(self) is not type(other):
            raise TypeError(f"无法合并不同类型的消息: {type(self)} 和 {type(other)}")

        content: list[ContentPartText | ContentPartImage] = []
        for msg in (self, other):
            if isinstance(msg.content, str):
                content.append(ContentPartText(text=msg.content))
            else:
                content.extend(msg.content)
        return type(self)(content=content)


@dataclasses.dataclass(frozen=True, slots=True)
class UserMessage(BaseMessage): ...


@dataclasses.dataclass(frozen=True, slots=True)
class SystemMessage(BaseMessage): ...


@dataclasses.dataclass(frozen=True, slots=True)
class AssistantMessage(BaseMessage): ...


type Message = UserMessage | SystemMessage | AssistantMessage
_ROLE_MAP: dict[type[Message], str] = {
    UserMessage: "user",
    SystemMessage: "system",
    AssistantMessage: "assistant",
}


def dump_messages(*messages: Message) -> list[dict[str, str]]:
    """将类型化的消息转换为 OpenAI API 格式。

    Returns:
        list[dict[str, str]]: 包含 role 和 content 的消息列表
    """
    result: list[dict[str, Any]] = []
    for msg in messages:
        msg_cls = type(msg)
        if msg_cls not in _ROLE_MAP:
            raise ValueError(f"未知消息类型: {msg_cls}")
        result.append({"role": _ROLE_MAP[msg_cls], "content": msg.dump_content()})
    return result


@dataclasses.dataclass(frozen=True, slots=True)
class CompletionTokensDetails:
    accepted_prediction_tokens: int = 0
    audio_tokens: int = 0
    reasoning_tokens: int = 0
    rejected_prediction_tokens: int = 0

    def __add__(self, other: CompletionTokensDetails) -> CompletionTokensDetails:
        return CompletionTokensDetails(
            accepted_prediction_tokens=self.accepted_prediction_tokens
            + other.accepted_prediction_tokens,
            audio_tokens=self.audio_tokens + other.audio_tokens,
            reasoning_tokens=self.reasoning_tokens + other.reasoning_tokens,
            rejected_prediction_tokens=self.rejected_prediction_tokens
            + other.rejected_prediction_tokens,
        )


@dataclasses.dataclass(frozen=True, slots=True)
class PromptTokensDetails:
    audio_tokens: int = 0
    cached_tokens: int = 0

    def __add__(self, other: PromptTokensDetails) -> PromptTokensDetails:
        return PromptTokensDetails(
            audio_tokens=self.audio_tokens + other.audio_tokens,
            cached_tokens=self.cached_tokens + other.cached_tokens,
        )


@dataclasses.dataclass(frozen=True, slots=True)
class TokenUsage:
    completion_tokens: int = 0
    prompt_tokens: int = 0
    total_tokens: int = 0
    completion_tokens_details: CompletionTokensDetails = dataclasses.field(
        default_factory=CompletionTokensDetails
    )
    prompt_tokens_details: PromptTokensDetails = dataclasses.field(
        default_factory=PromptTokensDetails
    )

    def __add__(self, other: TokenUsage) -> TokenUsage:
        return TokenUsage(
            prompt_tokens=self.prompt_tokens + other.prompt_tokens,
            completion_tokens=self.completion_tokens + other.completion_tokens,
            total_tokens=self.total_tokens + other.total_tokens,
            completion_tokens_details=self.completion_tokens_details
            + other.completion_tokens_details,
            prompt_tokens_details=self.prompt_tokens_details
            + other.prompt_tokens_details,
        )
