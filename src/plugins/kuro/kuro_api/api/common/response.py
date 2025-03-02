from collections.abc import Sequence
from typing import ClassVar, Literal, TypeGuard

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


type _CommonFailedResponse = FailedResponseWithMsg | FailedResponseWithMessage
type FailedResponse = TokenExpiredResponse | _CommonFailedResponse
type Response[T: ValidResponseData] = SuccessResponse[T] | FailedResponse


def is_success_response[T: ValidResponseData](
    response: Response[T],
) -> TypeGuard[SuccessResponse[T]]:
    return response.success


def is_failed_response[T: ValidResponseData](
    response: Response[T],
) -> TypeGuard[FailedResponse]:
    return not response.success
