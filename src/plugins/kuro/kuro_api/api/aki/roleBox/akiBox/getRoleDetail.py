# ruff: noqa: N815

from typing import override

from .....common import RequestInfo, ResponseData, WebRequest
from .....const import GameId, WuwaGameId


class Chain(ResponseData):
    description: str
    """共鸣链描述"""
    name: str
    """共鸣链名称"""
    order: int
    """共鸣链序号"""
    unlocked: bool
    """是否解锁"""


class FetterDetail(ResponseData):
    name: str
    """套装名称"""
    num: int
    """套装生效数量"""
    firstDescription: str
    """套装效果 1"""
    secondDescription: str
    """套装效果 2"""
    groupId: int
    iconUrl: str
    """套装图标"""


class PhantomProperties(ResponseData):
    cost: int
    """声骸 COST"""
    iconUrl: str
    """声骸图标 URL"""
    name: str
    """声骸名称

    异构武装
    """
    phantomId: int
    """声骸 ID

    6000083
    """
    phantomPropId: int
    """(?)

    60000835"""
    quality: int
    """声骸品质"""
    skillDescription: str
    """声骸技能描述"""


class PhantomAttribute(ResponseData):
    attributeName: str
    """属性名称"""
    attributeValue: str
    """属性值"""


class PhantomMainAttribute(PhantomAttribute):
    iconUrl: str
    """属性图标"""


class Phantom(ResponseData):
    cost: int
    """声骸 COST"""
    fetterDetail: FetterDetail
    """声骸套装效果"""
    level: int
    """声骸强化等级"""
    phantomProp: PhantomProperties
    """声骸属性"""
    quality: int
    """声骸品质

    金 = 5
    """
    mainProps: list[PhantomMainAttribute]
    """声骸主属性列表"""
    subProps: list[PhantomAttribute]
    """声骸副属性列表"""


class PhantomData(ResponseData):
    cost: int
    """声骸总 COST"""
    equipPhantomList: list[Phantom]
    """已装备的声骸列表"""


class Role(ResponseData):
    acronym: str
    """角色名称音序"""
    attributeId: int
    """属性 ID

    冷凝 = 1
    热熔 = 2
    导电 = 3
    气动 = 4
    衍射 = 5
    湮灭 = 6

    TODO: 枚举值
    """
    attributeName: str
    """属性名称"""
    breach: int
    """突破等级"""
    isMainRole: bool
    level: int
    """角色等级"""
    roleIconUrl: str
    roleId: int
    """角色 ID"""
    roleName: str
    """角色名"""
    rolePicUrl: str
    starLevel: int
    """星级"""
    weaponTypeId: int
    """武器类型 ID

    长刃 = 1
    迅刀 = 2
    配枪 = 3
    臂铠 = 4
    音感仪 = 5

    TODO: 枚举值
    """
    weaponTypeName: str
    """武器类型名称"""


class RoleSkin(ResponseData):
    isAddition: bool
    picUrl: str
    priority: int
    quality: int
    qualityName: str
    skinIcon: str
    skinId: int
    skinName: str


class SkillDetail(ResponseData):
    id: int
    """技能 ID"""
    name: str
    """技能名称"""
    type: str
    """技能类型"""
    description: str
    """技能描述"""


class Skill(ResponseData):
    level: int
    """技能等级"""
    skill: SkillDetail
    """技能详细信息"""


class WeaponDetail(ResponseData):
    weaponId: int
    """武器 ID"""
    weaponName: str
    """武器名称"""
    weaponStarLevel: int
    """武器星级"""
    weaponType: int
    """武器类型 ID

    参考角色信息的 weaponTypeId 字段

    TODO: 枚举值
    """
    weaponIcon: str
    """武器图标 URL"""
    weaponEffectName: str
    """武器效果名称"""
    effectDescription: str
    """效果描述"""


class WeaponData(ResponseData):
    breach: int
    """武器突破等级"""
    level: int
    """武器等级"""
    resonLevel: int
    """武器谐振等级"""
    weapon: WeaponDetail
    """武器详细信息"""


class RoleDetail(ResponseData):
    chainList: list[Chain]
    """共鸣链"""
    level: int
    """角色等级"""
    phantomData: PhantomData
    """声骸装备数据"""
    role: Role
    """角色数据"""
    roleSkin: RoleSkin
    """角色皮肤数据"""
    skillList: list[Skill]
    """技能列表"""
    weaponData: WeaponData
    """武器数据"""


class WuwaGetRoleDetailRequest(WebRequest[RoleDetail]):
    gameId: WuwaGameId = GameId.WUWA
    roleId: str
    serverId: str
    channelId: int = 19
    countryCode: int = 1
    id: int

    @override
    def get_info(self) -> RequestInfo:
        return RequestInfo(
            url="https://api.kurobbs.com/aki/roleBox/akiBox/getRoleDetail",
            method="POST",
        )

    @override
    def get_response_data_class(self) -> type[RoleDetail]:
        return RoleDetail
