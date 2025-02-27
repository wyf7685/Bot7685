# ruff: noqa: N815

from dataclasses import dataclass
from typing import final

from ...common import Request, RequestInfo, ResponseData


class Mine(ResponseData):
    collectCount: int
    commentCount: int
    fansCount: int
    fansNewCount: int
    followCount: int
    gender: int
    goldNum: int
    headUrl: str
    ifCompleteQuiz: int
    isFollow: int
    isLoginUser: int
    isMute: int
    lastLoginModelType: str
    lastLoginTime: str
    levelTotal: int
    likeCount: int
    medalList: list[object]
    mobile: str
    postCount: int
    registerTime: str
    signature: str
    signatureReviewStatus: int
    status: int
    userId: int
    userName: str


class MineV2(ResponseData):
    mine: Mine


@final
@dataclass
class MineV2Request(Request[MineV2]):
    """取个人信息 V2"""

    _info_ = RequestInfo(url="https://api.kurobbs.com/user/mineV2", method="POST")
    _resp_ = MineV2

    otherUserId: str = ""
