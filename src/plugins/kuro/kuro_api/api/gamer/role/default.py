# ruff: noqa: N815

from typing import override

from ....common import Request, RequestInfo, ResponseData
from .list import Role


class RoleDefault(ResponseData):
    defaultRole: object | None = None
    hasDefaultRole: bool
    hideRole: bool
    defaultRoleList: list[Role]


class RoleDefaultRequest(Request[RoleDefault]):
    queryUserId: str

    @override
    def get_info(self) -> RequestInfo:
        return RequestInfo(
            url="https://api.kurobbs.com/gamer/role/default",
            method="POST",
        )

    @override
    def get_response_data_class(self) -> type[RoleDefault]:
        return RoleDefault
