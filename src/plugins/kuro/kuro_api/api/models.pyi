from .aki.roleBox.akiBox.baseData import WuwaBaseDataRequest
from .aki.roleBox.akiBox.calabashData import WuwaCalabashDataRequest
from .aki.roleBox.akiBox.challengeDetails import WuwaChallengeDetailsRequest
from .aki.roleBox.akiBox.challengeIndex import WuwaChallengeIndexRequest
from .aki.roleBox.akiBox.exploreIndex import WuwaExploreIndexRequest
from .aki.roleBox.akiBox.getAllRole import WuwaGetAllRoleRequest
from .aki.roleBox.akiBox.getRoleDetail import (
    Phantom,
    PhantomAttribute,
    RoleDetail,
    WuwaGetRoleDetailRequest,
)
from .aki.roleBox.akiBox.getShowSettings import WuwaGetShowSettingsRequest
from .aki.roleBox.akiBox.refreshData import WuwaRefreshDataRequest
from .aki.roleBox.akiBox.roleData import WuwaRoleDataRequest
from .aki.roleBox.akiBox.skinData import WuwaSkinDataRequest
from .aki.roleBox.akiBox.towerDataDetail import WuwaTowerDataDetailRequest
from .aki.roleBox.akiBox.towerIndex import WuwaTowerIndexRequest
from .aki.roleBox.akiBox.updateShowRoleSetting import WuwaUpdateShowRoleSettingRequest
from .aki.roleBox.akiBox.updateShowSetting import WuwaUpdateShowSettingRequest
from .config.dict.getSdkLoginUrl import GetSdkLoginUrlRequest
from .config.dict.timingSwitch import TimingSwitchRequest
from .config.getOpenScreen import GetOpenScreenRequest
from .encourage.gold.getGoldLogs import GetGoldLogsRequest
from .encourage.gold.getTotalGold import GetTotalGoldRequest
from .encourage.signIn.initSignInV2 import InitSigninV2Request
from .encourage.signIn.queryRecordV2 import QueryRecordV2Request
from .encourage.signIn.v2 import SigninV2Request
from .forum.dynamic.isRedPoint import IsRedPointRequest
from .gamer.role.default import RoleDefaultRequest
from .gamer.role.list import (
    PnsRole,
    PnsRoleListRequest,
    Role,
    RoleListRequest,
    WuwaRole,
    WuwaRoleListRequest,
)
from .gamer.role.queryUserId import QueryUserIdRequest
from .gamer.widget.game3.getData import WuwaWidgetGetDataRequest
from .user.center.init import UserCenterInitRequest
from .user.getSmsCode import GetSmsCodeRequest
from .user.login.log import UserLoginLogRequest
from .user.mineV2 import Mine, MineV2Request
from .user.role.findRoleList import FindRoleListRequest
from .user.sdkLogin import SdkLoginRequest
from .user.sdkLoginForH5 import SdkLoginForH5Request
from .user.sdkLogout import SdkLogoutRequest
from .user.signIn import SignInRequest
from .user.signInInfo import SignInInfoRequest

__all__ = [
    "FindRoleListRequest",
    "GetGoldLogsRequest",
    "GetOpenScreenRequest",
    "GetSdkLoginUrlRequest",
    "GetSmsCodeRequest",
    "GetTotalGoldRequest",
    "InitSigninV2Request",
    "IsRedPointRequest",
    "Mine",
    "MineV2Request",
    "Phantom",
    "PhantomAttribute",
    "PnsRole",
    "PnsRoleListRequest",
    "QueryRecordV2Request",
    "QueryUserIdRequest",
    "Role",
    "RoleDefaultRequest",
    "RoleDetail",
    "RoleListRequest",
    "SdkLoginForH5Request",
    "SdkLoginRequest",
    "SdkLogoutRequest",
    "SignInInfoRequest",
    "SignInRequest",
    "SigninV2Request",
    "TimingSwitchRequest",
    "UserCenterInitRequest",
    "UserLoginLogRequest",
    "WuwaBaseDataRequest",
    "WuwaCalabashDataRequest",
    "WuwaChallengeDetailsRequest",
    "WuwaChallengeIndexRequest",
    "WuwaExploreIndexRequest",
    "WuwaGetAllRoleRequest",
    "WuwaGetRoleDetailRequest",
    "WuwaGetShowSettingsRequest",
    "WuwaRefreshDataRequest",
    "WuwaRole",
    "WuwaRoleDataRequest",
    "WuwaRoleListRequest",
    "WuwaSkinDataRequest",
    "WuwaTowerDataDetailRequest",
    "WuwaTowerIndexRequest",
    "WuwaUpdateShowRoleSettingRequest",
    "WuwaUpdateShowSettingRequest",
    "WuwaWidgetGetDataRequest",
]

