# ruff: noqa: N815
import dataclasses
import datetime
from collections import Counter
from urllib.parse import parse_qs, urlparse

import httpx

from ..exceptions import InvalidGachaUrl, KuroApiException
from .const import GACHA_HEADERS, GACHA_QUERY_URL
from .model import (
    CARD_POOL_NAME,
    WWGF,
    CardPoolType,
    GachaItem,
    GachaParams,
    GachaResponse,
    WWGFInfo,
    WWGFItem,
)


def parse_gacha_url(url: str) -> GachaParams:
    parsed = urlparse(url.replace("#", ""))
    query = parse_qs(parsed.query)
    return GachaParams(
        cardPoolId=query["gacha_id"][0],
        cardPoolType=int(query["gacha_type"][0]),
        languageCode=query["lang"][0],
        playerId=query["player_id"][0],
        recordId=query["record_id"][0],
        serverId=query["svr_id"][0],
    )


class WuwaGachaApi:
    _url: str
    _params: GachaParams

    def __init__(self, gacha_url: str) -> None:
        for head, query_url in GACHA_QUERY_URL.items():
            if gacha_url.startswith(head):
                self._url = f"{query_url}/gacha/record/query"
                break
        else:
            raise InvalidGachaUrl(f"无效的抽卡 URL: {gacha_url}")

        try:
            self._params = parse_gacha_url(gacha_url)
        except KeyError as err:
            raise InvalidGachaUrl(f"无效的抽卡 URL: {gacha_url}") from err

    async def _query(self, type_: CardPoolType) -> GachaResponse:
        self._params.cardPoolType = type_
        async with httpx.AsyncClient() as client:
            response = await client.post(
                self._url,
                headers=GACHA_HEADERS,
                json=dataclasses.asdict(self._params),
            )
            data = response.raise_for_status().read()

        try:
            return GachaResponse.model_validate_json(data)
        except Exception as err:
            raise KuroApiException("获取抽卡数据失败") from err

    def _convert(
        self,
        card_pool_type: CardPoolType,
        items: list[GachaItem],
    ) -> list[WWGFItem]:
        time_count = Counter(item.timestamp for item in items)

        result: list[WWGFItem] = []
        for item in items:
            gacha_id = f"{card_pool_type.value:04d}"
            id = f"{item.timestamp}{gacha_id}{time_count[item.timestamp]:05d}"
            time_count[item.timestamp] -= 1
            result.append(
                WWGFItem(
                    gacha_id=gacha_id,
                    gacha_type=CARD_POOL_NAME[card_pool_type],
                    item_id=str(item.resourceId),
                    count=str(item.count),
                    time=item.time,
                    name=item.name,
                    item_type=item.resourceType,
                    rank_type=str(item.qualityLevel),
                    id=id,
                )
            )

        return result

    async def fetch_wwgf(self) -> WWGF:
        items: list[WWGFItem] = []

        for i in CardPoolType:
            resp = await self._query(i)
            items.extend(self._convert(i, resp.data))

        info = WWGFInfo(
            uid=self._params.playerId,
            export_timestamp=int(datetime.datetime.now().timestamp()),
        )

        wwgf = WWGF(info=info, list=items)
        wwgf.sort()

        return wwgf
