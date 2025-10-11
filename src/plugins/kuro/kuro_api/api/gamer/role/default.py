# ruff: noqa: N815

from typing import final

from ...common import Request, RequestInfo, ResponseData
from .list import Role


class RoleDefault(ResponseData):
    defaultRole: object | None = None
    hasDefaultRole: bool
    hideRole: bool
    defaultRoleList: list[Role]


@final
class RoleDefaultRequest(Request[RoleDefault]):
    _info_ = RequestInfo(
        url="https://api.kurobbs.com/gamer/role/default",
        method="POST",
    )
    _resp_ = RoleDefault

    queryUserId: str
