_LOCATION = {
    # Requests
    "WuwaBaseDataRequest": "aki.roleBox.akiBox.baseData",
    "WuwaCalabashDataRequest": "aki.roleBox.akiBox.calabashData",
    "WuwaChallengeDetailsRequest": "aki.roleBox.akiBox.challengeDetails",
    "WuwaChallengeIndexRequest": "aki.roleBox.akiBox.challengeIndex",
    "WuwaExploreIndexRequest": "aki.roleBox.akiBox.exploreIndex",
    "WuwaGetAllRoleRequest": "aki.roleBox.akiBox.getAllRole",
    "WuwaGetRoleDetailRequest": "aki.roleBox.akiBox.getRoleDetail",
    "WuwaRefreshDataRequest": "aki.roleBox.akiBox.refreshData",
    "WuwaRoleDataRequest": "aki.roleBox.akiBox.roleData",
    "WuwaSkinDataRequest": "aki.roleBox.akiBox.skinData",
    "WuwaTowerDataDetailRequest": "aki.roleBox.akiBox.towerDataDetail",
    "WuwaTowerIndexRequest": "aki.roleBox.akiBox.towerIndex",
    "GetTotalGoldRequest": "encourage.gold.getTotalGold",
    "InitSigninV2Request": "encourage.signIn.initSignInV2",
    "QueryRecordV2Request": "encourage.signIn.queryRecordV2",
    "SigninV2Request": "encourage.signIn.v2",
    "RoleDefaultRequest": "gamer.role.default",
    "RoleListRequest": "gamer.role.list",
    "PnsRoleListRequest": "gamer.role.list",
    "WuwaRoleListRequest": "gamer.role.list",
    "QueryUserIdRequest": "gamer.role.queryUserId",
    "WuwaWidgetGetDataRequest": "gamer.widget.game3.getData",
    "GetSmsCodeRequest": "user.getSmsCode",
    "MineV2Request": "user.mineV2",
    "FindRoleListRequest": "user.role.findRoleList",
    "SdkLoginRequest": "user.sdkLogin",
    "SdkLoginForH5Request": "user.sdkLoginForH5",
    "SignInRequest": "user.signIn",
    "SignInInfoRequest": "user.signInInfo",
    # Models
    "Phantom": "aki.roleBox.akiBox.getRoleDetail",
    "PhantomAttribute": "aki.roleBox.akiBox.getRoleDetail",
    "RoleDetail": "aki.roleBox.akiBox.getRoleDetail",
    "PnsRole": "gamer.role.list",
    "Role": "gamer.role.list",
    "WuwaRole": "gamer.role.list",
    "Mine": "user.mineV2",
}
_CACHE: dict[str, object] = {}
__all__ = list(_LOCATION.keys())  # pyright:ignore[reportUnsupportedDunderAll]


def __getattr__(name: str) -> object:
    if name in _LOCATION:
        if name not in _CACHE:
            import importlib

            module = importlib.import_module(f".{_LOCATION[name]}", __package__)
            _CACHE[name] = getattr(module, name)
        return _CACHE[name]
    if name in globals():
        return globals()[name]
    raise AttributeError(f"module {__name__} has no attribute {name}")
