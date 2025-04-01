from collections.abc import Callable
from typing import final

import anyio
import anyio.to_thread
from tencentcloud.common import credential
from tencentcloud.dnspod.v20210323 import dnspod_client, models

from ..config import plugin_config
from .model import DescribeRecordListResponse, ModifyRecordResponse, Response

config = plugin_config.tencent


@final
class TencentClient:
    def __init__(self) -> None:
        cred = credential.Credential(
            secret_id=config.credential.secret_id.get_secret_value(),
            secret_key=config.credential.secret_key.get_secret_value(),
        )
        self.client = dnspod_client.DnspodClient(cred, "")

    async def _request[
        T: models.AbstractModel,
        S: models.AbstractModel,
        R: Response,
    ](
        self,
        call: Callable[[T], S],
        req: T,
        model: type[R],
    ) -> R:
        resp = await anyio.to_thread.run_sync(call, req)
        obj = resp._serialize(allow_none=True)  # noqa: SLF001 # pyright: ignore[reportPrivateUsage]
        return model.model_validate(obj)

    async def _describe_record_list(
        self,
        domain: str,
        sub_domain: str,
    ) -> DescribeRecordListResponse:
        request = models.DescribeRecordListRequest()
        request.Domain = domain
        request.Subdomain = sub_domain
        return await self._request(
            self.client.DescribeRecordList,
            request,
            DescribeRecordListResponse,
        )

    async def _modify_record(
        self,
        domain: str,
        sub_domain: str,
        record_id: int,
        value: str,
    ) -> ModifyRecordResponse:
        request = models.ModifyRecordRequest()
        request.Domain = domain
        request.SubDomain = sub_domain
        request.RecordType = "A"
        request.RecordLine = "默认"
        request.RecordId = record_id
        request.Value = value
        return await self._request(
            self.client.ModifyRecord,
            request,
            ModifyRecordResponse,
        )

    async def update_record(self, value: str) -> None:
        resp = await self._describe_record_list(config.domain, config.sub_domain)
        record_id = resp.RecordList[0].RecordId
        await self._modify_record(config.domain, config.sub_domain, record_id, value)
