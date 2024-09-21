# ruff: noqa: N801, N815

from typing import Any, Literal

from pydantic import BaseModel, Field


class DailySignAward(BaseModel):
    name: str
    count: int


class DailySignResult(BaseModel):
    status: Literal["success", "failed"] = Field()
    message: str = Field()
    awards: list[DailySignAward] = Field(default_factory=list)


class _ArkUserInfo_user(BaseModel):
    id: str
    nickname: str
    profile: str
    avatarCode: int
    avatar: str
    backgroundCode: int
    isCreator: bool
    creatorIdentifiers: list[Any]
    status: int
    operationStatus: int
    identity: int
    kind: int
    latestIpLocation: str
    moderatorStatus: int
    moderatorChangeTime: int
    gender: int
    birthday: str


class _ArkUserInfo_userRts(BaseModel):
    liked: str
    collect: str
    comment: str
    follow: str
    fans: str
    black: str
    pub: str


class _ArkUserInfo_gameStatus_avatar(BaseModel):
    type: str
    id: str


class _ArkUserInfo_gameStatus_secretary(BaseModel):
    charId: str
    skinId: str


class _ArkUserInfo_gameStatus_ap(BaseModel):
    current: int
    max: int
    lastApAddTime: int
    completeRecoveryTime: int


class _ArkUserInfo_gameStatus(BaseModel):
    uid: str
    name: str
    level: int
    avatar: _ArkUserInfo_gameStatus_avatar
    registerTs: int
    mainStageProgress: str
    secretary: _ArkUserInfo_gameStatus_secretary
    resume: str
    subscriptionEnd: int
    ap: _ArkUserInfo_gameStatus_ap
    storeTs: int
    lastOnlineTs: int
    charCnt: int
    furnitureCnt: int
    skinCnt: int


class _ArkUserInfo_moderator(BaseModel):
    isModerator: bool


class _ArkUserInfo_userInfoApply(BaseModel):
    nickname: str
    profile: str


class ArkUserInfo(BaseModel):
    user: _ArkUserInfo_user
    userRts: _ArkUserInfo_userRts
    userSanctionList: list[Any]
    gameStatus: _ArkUserInfo_gameStatus
    moderator: _ArkUserInfo_moderator
    userInfoApply: _ArkUserInfo_userInfoApply


class _BindInfo_item(BaseModel):
    uid: str
    isOfficial: bool
    isDefault: bool
    channelMasterId: str
    channelName: str
    nickName: str
    isDelete: bool


class BindInfo(BaseModel):
    appCode: str
    appName: str
    defaultUid: str
    bindingList: list[_BindInfo_item]
