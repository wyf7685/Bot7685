from collections.abc import AsyncGenerator

import anyio
import nonebot
from alibabacloud_openapi_util.client import Client as OpenApiUtilClient
from alibabacloud_tea_openapi import models as open_api_models
from alibabacloud_tea_openapi.client import Client as OpenApiClient
from alibabacloud_tea_util import models as util_models

from ..config import plugin_config
from .model import (
    DescribeInstancesRequest,
    DescribeInstanceStatusRequest,
    InstanceInfo,
    InstanceStatus,
    Request,
    Response,
    ResponseBody,
    ResponseHeaders,
    RunInstancesRequest,
)

config = plugin_config.ali
logger = nonebot.logger.opt(colors=True)


class AliClient:
    def __init__(self) -> None:
        sdk_config = open_api_models.Config(
            access_key_id=config.credential.access_key_id.get_secret_value(),
            access_key_secret=config.credential.access_key_secret.get_secret_value(),
            region_id=config.region_id,
            endpoint=f"ecs.{config.region_id}.aliyuncs.com",
        )
        self.client = OpenApiClient(sdk_config)

    @staticmethod
    def create_api_info(action: str) -> open_api_models.Params:
        return open_api_models.Params(
            action=action,
            version="2014-05-26",
            protocol="HTTPS",
            method="POST",
            auth_type="AK",
            style="RPC",
            pathname="/",
            req_body_type="json",
            body_type="json",
        )

    async def _request[B: ResponseBody, H: ResponseHeaders](
        self, request: Request[B, H]
    ) -> Response[B, H]:
        action = request.action
        query = OpenApiUtilClient.query(request.model_dump(exclude_none=True))
        response = await self.client.call_api_async(
            params=self.create_api_info(action),
            request=open_api_models.OpenApiRequest(query=query),
            runtime=util_models.RuntimeOptions(),
        )
        return request.parse_response(response)

    async def describe_instance_status(self, inst_id: str) -> InstanceStatus:
        request = DescribeInstanceStatusRequest(
            RegionId=config.region_id,
            InstanceIds=[inst_id],
        )
        resp = await self._request(request)
        if data := resp.body.InstanceStatuses.InstanceStatus:
            return data[0].Status

        raise ValueError(f"Instance {inst_id} not found")

    async def create_instance_from_template(self) -> str:
        if inst := await self.find_instance_by_name(config.instance_name):
            logger.info(f"Instance <c>{inst.InstanceId}</c> already exists")
            return inst.InstanceId

        request = RunInstancesRequest(
            RegionId=config.region_id,
            Amount=1,
            LaunchTemplateId=config.template_id,
            InstanceName=config.instance_name,
        )
        resp = await self._request(request)
        inst_id = resp.body.InstanceIdSets.InstanceIdSet[0]
        logger.info(f"Instance <c>{inst_id}</c> created")

        while True:
            status = await self.describe_instance_status(inst_id)
            logger.info(f"Instance <c>{inst_id}</c> status: {status}")

            if status == InstanceStatus.RUNNING:
                break

            await anyio.sleep(10)

        return inst_id

    async def describe_instances(self, *inst_id: str) -> AsyncGenerator[InstanceInfo]:
        next_token = None

        while next_token is None or next_token:
            request = DescribeInstancesRequest(
                RegionId=config.region_id,
                InstanceIds=list(inst_id) if inst_id else None,
                NextToken=next_token,
                MaxResults=1,
            )
            resp = await self._request(request)
            if not (instances := resp.body.Instances.Instance):
                return

            yield instances[0]

            next_token = resp.body.NextToken

    async def find_instance_by_name(self, name: str) -> InstanceInfo | None:
        async for info in self.describe_instances():
            if info.InstanceName == name:
                return info
        return None
