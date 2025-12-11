# ruff: noqa: N815
from pydantic import BaseModel, Field


class SenderInfo(BaseModel):
    """发送者信息"""

    uin: str | int = Field(description="用户唯一标识符 (UIN)")
    name: str = Field(default="", description="用户名称")


class ReplyInfo(BaseModel):
    """回复信息"""

    referencedMessageId: str = Field(description="被回复消息的 ID")


class ContentInfo(BaseModel):
    """消息内容"""

    text: str = Field(default="", description="消息文本内容")
    reply: ReplyInfo | None = Field(default=None, description="回复信息（可选）")


class TextElement(BaseModel):
    """文本元素（用于 @）"""

    atType: int = Field(default=0, description="@ 类型")
    atUid: str = Field(default="", description="被@用户ID")


class MessageElement(BaseModel):
    """消息元素"""

    elementType: int = Field(description="元素类型，1=文本")
    textElement: TextElement | None = Field(
        default=None, description="文本元素（当elementType=1时）"
    )


class RawMessage(BaseModel):
    """原始消息信息"""

    subMsgType: int = Field(default=0, description="消息子类型（577/65 为机器人消息）")
    sendMemberName: str | None = Field(default=None, description="发送者的成员名称")
    elements: list[MessageElement] = Field(
        default_factory=list, description="消息元素数组"
    )


class Message(BaseModel):
    """单条消息"""

    messageId: str = Field(description="消息唯一ID")
    sender: SenderInfo = Field(description="发送者信息")
    content: ContentInfo = Field(description="消息内容")
    timestamp: str = Field(default="", description="消息时间戳")
    rawMessage: RawMessage = Field(
        default_factory=RawMessage, description="原始消息信息"
    )


class ChatInfo(BaseModel):
    """群聊信息"""

    name: str | None = Field(default=None, description="群聊名称")


class AnalyzerInput(BaseModel):
    """ChatAnalyzer 输入数据模型"""

    messages: list[Message] = Field(description="消息列表")
    chatName: str | None = Field(default=None, description="群聊名称（优先级高）")
    chatInfo: ChatInfo | None = Field(default=None, description="群聊信息")
