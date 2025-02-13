# ruff: noqa: ANN201
from __future__ import annotations

import contextlib
import dataclasses
import datetime
import functools
from typing import TYPE_CHECKING, Protocol, Self, overload

from ..exceptions import AlreadySignin, ApiCallFailed, KuroApiException, RoleNotFound

if TYPE_CHECKING:
    from collections.abc import Sequence

    from ..common import Response, ValidResponseData
    from ..common.request import Request
    from ..const import PnsGameId, WuwaGameId
    from .gamer.role.list import PnsRole, Role, WuwaRole
    from .user.mineV2 import Mine

    type GameId = PnsGameId | WuwaGameId


def _extract[T: ValidResponseData](resp: Response[T]) -> T:
    # 使用 if resp.success is True 时
    #   type checker 可以正常推断 resp 的类型为 SuccessResponse[T]
    # 但使用 if resp.success 时则不能
    # 看上去很怪但先用着罢

    if resp.success is True:
        return resp.data

    raise ApiCallFailed(resp.msg)


class KuroApi:
    token: str
    _mine_cache: Mine | None = None

    def __init__(self, token: str) -> None:
        self.token = token

    @classmethod
    def from_token(cls, token: str) -> Self:
        return cls(token)

    @classmethod
    async def from_mobile_code(cls, mobile: str, code: str) -> Self:
        from .user.sdkLogin import SdkLoginRequest

        resp = await SdkLoginRequest(mobile=mobile, code=code).send()
        return cls(_extract(resp).token)

    async def mine(self) -> Mine:
        from .user.mineV2 import MineV2Request

        if self._mine_cache is None:
            resp = await MineV2Request().send(self.token)
            self._mine_cache = _extract(resp).mine
        return self._mine_cache

    async def get_user_name(self) -> str:
        return (await self.mine()).userName

    async def get_user_id(self) -> int:
        return (await self.mine()).userId

    async def get_gold_num(self) -> int:
        return (await self.mine()).goldNum

    async def has_signin(self) -> bool:
        from .user.signInInfo import SignInInfoRequest

        resp = await SignInInfoRequest().send(self.token)
        return _extract(resp).hasSignIn

    async def signin(self):
        from .user.signIn import SignInRequest

        resp = await SignInRequest().send(self.token)
        return _extract(resp)

    @overload
    async def role_list(self, game_id: PnsGameId) -> Sequence[PnsRole]: ...
    @overload
    async def role_list(self, game_id: WuwaGameId) -> Sequence[WuwaRole]: ...

    async def role_list(self, game_id: GameId) -> Sequence[Role]:
        from .gamer.role.list import RoleListRequest

        resp = await RoleListRequest(gameId=game_id).send(self.token)
        return _extract(resp)

    @overload
    async def find_default_role(self, game_id: PnsGameId) -> PnsRole: ...
    @overload
    async def find_default_role(self, game_id: WuwaGameId) -> WuwaRole: ...

    async def find_default_role(self, game_id: GameId) -> Role:
        role_list = await self.role_list(game_id)
        for role in role_list:
            if role.isDefault:
                return role

        raise RoleNotFound(f"未找到默认角色: {game_id=}")

    @overload
    def get_role_api(self, role: PnsRole) -> KuroRoleApi: ...
    @overload
    def get_role_api(self, role: WuwaRole) -> KuroWuwaRoleApi: ...

    def get_role_api(self, role: Role) -> KuroRoleApi | KuroWuwaRoleApi:
        from .gamer.role.list import PnsRole, WuwaRole

        match role:
            case WuwaRole():
                return KuroWuwaRoleApi(self.token, role)
            case PnsRole():
                return KuroRoleApi(self.token, role)

    @overload
    async def get_default_role_api(self, game_id: PnsGameId) -> KuroRoleApi: ...
    @overload
    async def get_default_role_api(self, game_id: WuwaGameId) -> KuroWuwaRoleApi: ...

    async def get_default_role_api(
        self, game_id: GameId
    ) -> KuroRoleApi | KuroWuwaRoleApi:
        role = await self.find_default_role(game_id)
        return self.get_role_api(role)


@dataclasses.dataclass
class GoodsData:
    name: str
    num: int


class KuroRoleApi[R: Role = Role]:
    token: str
    role: R

    def __init__(self, token: str, role: R) -> None:
        self.token = token
        self.role = role

    async def signin(self) -> list[GoodsData]:
        from .encourage.signIn.initSignInV2 import InitSigninV2Request
        from .encourage.signIn.queryRecordV2 import QueryRecordV2Request
        from .encourage.signIn.v2 import SigninV2Request

        now = datetime.datetime.now()
        resp = await InitSigninV2Request(
            gameId=self.role.gameId,
            serverId=self.role.serverId,
            roleId=self.role.roleId,
            userId=str(self.role.userId),
        ).send(self.token)

        if _extract(resp).isSignIn:
            raise AlreadySignin("今日已签到")

        resp = await SigninV2Request(
            gameId=self.role.gameId,
            serverId=self.role.serverId,
            roleId=self.role.roleId,
            userId=str(self.role.userId),
            reqMonth=now.month,
        ).send(self.token)
        goods = [
            GoodsData(name=str(item.goodsId), num=item.goodsNum)
            for item in _extract(resp).todayList
        ]

        with contextlib.suppress(KuroApiException):
            resp = await QueryRecordV2Request(
                gameId=self.role.gameId,
                serverId=self.role.serverId,
                roleId=self.role.roleId,
                userId=str(self.role.userId),
            ).send(self.token)
            today = now.strftime("%Y-%m-%d")
            goods = [
                GoodsData(name=item.goodsName, num=item.goodsNum)
                for item in sorted(_extract(resp), key=lambda x: (x.type, x.signInDate))
                if item.signInDate.startswith(today)
            ]

        return goods


class _WuwaFetchReq[T: ValidResponseData](Protocol):
    def __call__(self, *, roleId: str, serverId: str) -> Request[T]: ...  # noqa: N803


class KuroWuwaRoleApi(KuroRoleApi["WuwaRole"]):
    async def _fetch_with[T: ValidResponseData](self, req: _WuwaFetchReq[T], /) -> T:
        resp = await req(
            roleId=self.role.roleId,
            serverId=self.role.serverId,
        ).send(self.token)
        return _extract(resp)

    async def get_widget_data(self):
        from .gamer.widget.game3.getData import WuwaWidgetGetDataRequest

        return await self._fetch_with(WuwaWidgetGetDataRequest)

    async def get_energy(self):
        widget = await self.get_widget_data()
        return widget.energyData.cur, widget.energyData.total

    async def get_base_data(self):
        from .aki.roleBox.akiBox.baseData import WuwaBaseDataRequest

        return await self._fetch_with(WuwaBaseDataRequest)

    async def get_calabash_data(self):
        from .aki.roleBox.akiBox.calabashData import WuwaCalabashDataRequest

        return await self._fetch_with(WuwaCalabashDataRequest)

    async def get_challenge_index(self):
        from .aki.roleBox.akiBox.challengeIndex import WuwaChallengeIndexRequest

        return await self._fetch_with(WuwaChallengeIndexRequest)

    async def get_challenge_details(self):
        from .aki.roleBox.akiBox.challengeDetails import WuwaChallengeDetailsRequest

        return await self._fetch_with(WuwaChallengeDetailsRequest)

    async def get_explore_index(self):
        from .aki.roleBox.akiBox.exploreIndex import WuwaExploreIndexRequest

        return await self._fetch_with(WuwaExploreIndexRequest)

    async def get_all_role(self):
        from .aki.roleBox.akiBox.getAllRole import WuwaGetAllRoleRequest

        return await self._fetch_with(WuwaGetAllRoleRequest)

    async def get_role_data(self):
        from .aki.roleBox.akiBox.roleData import WuwaRoleDataRequest

        return await self._fetch_with(WuwaRoleDataRequest)

    async def get_role_detail(self, role_id: int):
        from .aki.roleBox.akiBox.getRoleDetail import WuwaGetRoleDetailRequest

        call = functools.partial(WuwaGetRoleDetailRequest, id=role_id)
        return await self._fetch_with(call)

    async def get_skin_data(self):
        from .aki.roleBox.akiBox.skinData import WuwaSkinDataRequest

        return await self._fetch_with(WuwaSkinDataRequest)

    async def get_tower_data_detail(self):
        from .aki.roleBox.akiBox.towerDataDetail import WuwaTowerDataDetailRequest

        return await self._fetch_with(WuwaTowerDataDetailRequest)

    async def get_tower_index(self):
        from .aki.roleBox.akiBox.towerIndex import WuwaTowerIndexRequest

        return await self._fetch_with(WuwaTowerIndexRequest)

    async def refresh_data(self):
        from .aki.roleBox.akiBox.refreshData import WuwaRefreshDataRequest

        call = functools.partial(WuwaRefreshDataRequest, gameId=self.role.gameId)
        return await self._fetch_with(call)
