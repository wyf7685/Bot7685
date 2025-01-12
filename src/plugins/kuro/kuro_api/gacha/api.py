# ruff: noqa: N815
import dataclasses
import datetime
from collections import defaultdict
from urllib.parse import parse_qs, urlparse

import httpx

from ..const import VERSION
from ..exceptions import InvalidGachaUrl
from .const import CARD_POOL_NAME, GACHA_HEADERS, GACHA_QUERY_URL
from .model import (
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
        for k, v in GACHA_QUERY_URL.items():
            if k in gacha_url:
                self._url = v
                break
        else:
            raise InvalidGachaUrl(f"无效的抽卡 URL: {gacha_url}")

        self._params = parse_gacha_url(gacha_url)

    async def query_gacha_record(self, type_: CardPoolType) -> GachaResponse:
        self._params.cardPoolType = type_
        async with httpx.AsyncClient() as client:
            response = await client.post(
                self._url,
                headers=GACHA_HEADERS,
                json=dataclasses.asdict(self._params),
            )
            data = response.raise_for_status().read()
            return GachaResponse.model_validate_json(data)

    def convert_gachalog_format(
        self,
        card_pool_type: CardPoolType,
        items: list[GachaItem],
    ) -> list[WWGFItem]:
        time_count = defaultdict[str, int](lambda: 0)
        for item in items:
            time_count[item.time] += 1

        result: list[WWGFItem] = []
        for item in items:
            time = datetime.datetime.fromisoformat(item.time).timestamp()
            id = f"{int(time)}{card_pool_type.value:04d}{time_count[item.time]:05d}"
            time_count[item.time] -= 1
            result.append(
                WWGFItem(
                    gacha_id=str(card_pool_type.value),
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
            resp = await self.query_gacha_record(i)
            items.extend(self.convert_gachalog_format(i, resp.data))

        info = WWGFInfo(
            uid=self._params.playerId,
            export_timestamp=int(datetime.datetime.now().timestamp()),
            export_app="wyf7685/kuro-api",
            export_app_version=VERSION,
        )

        wwgf = WWGF(info=info, list=items)
        wwgf.sort()

        return wwgf
