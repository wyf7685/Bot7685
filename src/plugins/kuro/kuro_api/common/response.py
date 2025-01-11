from collections.abc import Sequence
from typing import ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field


class ResponseData(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="allow")


type ValidResponseData = ResponseData | Sequence[ValidResponseData] | str | bool | int


class SuccessResponse[T: ValidResponseData](BaseModel):
    code: Literal[200]
    msg: str
    success: Literal[True]
    data: T


class TokenExpiredResponse(BaseModel):
    code: Literal[220]
    msg: str
    success: Literal[False] = False


class FailedResponseWithMsg(BaseModel):
    code: int
    msg: str
    success: Literal[False] = False


class FailedResponseWithMessage(BaseModel):
    code: int
    msg: str = Field(alias="message")
    success: Literal[False] = False


type FailedResponse = (
    TokenExpiredResponse | FailedResponseWithMsg | FailedResponseWithMessage
)
type Response[T: ValidResponseData] = SuccessResponse[T] | FailedResponse
