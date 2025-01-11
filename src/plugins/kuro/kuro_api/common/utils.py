from typing import TypeGuard

from .response import FailedResponse, SuccessResponse, ValidResponseData


def is_success_response[T: ValidResponseData](
    response: SuccessResponse[T] | FailedResponse,
) -> TypeGuard[SuccessResponse[T]]:
    return response.success


def is_failed_response[T: ValidResponseData](
    response: SuccessResponse[T] | FailedResponse,
) -> TypeGuard[FailedResponse]:
    return not response.success
