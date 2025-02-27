# ruff: noqa: N815

from dataclasses import dataclass
from enum import Enum
from typing import Literal, final, override

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

    @property
    def is_main(self) -> bool:
        return False


class PhantomMainAttribute(PhantomAttribute):
    iconUrl: str
    """属性图标"""

    @property
    @override
    def is_main(self) -> Literal[True]:
        return True


class Phantom(ResponseData):
    cost: Literal[4, 3, 1]
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
    mainProps: list[PhantomMainAttribute] | None = None
    """声骸主属性列表"""
    subProps: list[PhantomAttribute] | None = None
    """声骸副属性列表"""

    def get_props(self) -> list[PhantomAttribute]:
        return [*(self.mainProps or []), *(self.subProps or [])]


class PhantomData(ResponseData):
    cost: int
    """声骸总 COST"""
    equipPhantomList: list[Phantom | None] | None = None
    """已装备的声骸列表"""


class AttributeID(int, Enum):
    GLACIO = 1
    """冷凝"""
    FUSION = 2
    """热熔"""
    ELECTRO = 3
    """导电"""
    AERO = 4
    """气动"""
    SPECTRO = 5
    """衍射"""
    HAVOC = 6
    """湮灭"""


class WeaponTypeID(int, Enum):
    BROADBLADE = 1
    """长刃"""
    SWORD = 2
    """迅刀"""
    PISTOLS = 3
    """配枪"""
    GAUNTLETS = 4
    """臂铠"""
    RECTIFIER = 5
    """音感仪"""


class Role(ResponseData):
    acronym: str
    """角色名称音序"""
    attributeId: AttributeID
    """属性 ID"""
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
    weaponTypeId: WeaponTypeID
    """武器类型 ID"""
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
    type: Literal[
        "常态攻击",
        "共鸣技能",
        "共鸣回路",
        "共鸣解放",
        "变奏技能",
        "延奏技能",
    ]
    """技能类型"""
    description: str
    """技能描述"""


skill_index = [
    "常态攻击",
    "共鸣技能",
    "共鸣回路",
    "共鸣解放",
    "变奏技能",
    "延奏技能",
].index


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
    weaponType: WeaponTypeID
    """武器类型 ID"""
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
    phantomData: PhantomData | None
    """声骸装备数据"""
    role: Role
    """角色数据"""
    roleSkin: RoleSkin
    """角色皮肤数据"""
    skillList: list[Skill]
    """技能列表"""
    weaponData: WeaponData
    """武器数据"""

    @property
    def sorted_skill(self) -> list[Skill]:
        return sorted(self.skillList, key=lambda x: skill_index(x.skill.type))


@final
@dataclass
class WuwaGetRoleDetailRequest(WebRequest[RoleDetail]):
    _info_ = RequestInfo(
        url="https://api.kurobbs.com/aki/roleBox/akiBox/getRoleDetail",
        method="POST",
    )
    _resp_ = RoleDetail

    roleId: str
    serverId: str
    id: int
    gameId: WuwaGameId = GameId.WUWA
    channelId: int = 19
    countryCode: int = 1
