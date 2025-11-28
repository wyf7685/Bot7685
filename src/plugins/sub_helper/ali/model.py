import enum

from pydantic import BaseModel


class Credential(BaseModel):
    access_key_id: str
    access_key_secret: str


class Config(BaseModel):
    credential: Credential
    region_id: str
    template_id: str
    instance_name: str


class ResponseHeaders(BaseModel):
    """Basic ResponseHeaders"""


class ResponseBody(BaseModel):
    """Basic ResponseBody"""

    RequestId: str


class Paginated(BaseModel):
    """Mixin for paginated ResponseBody"""

    TotalCount: int
    PageSize: int
    PageNumber: int
    NextToken: str = ""


class Response[B: ResponseBody, H: ResponseHeaders](BaseModel):
    statusCode: int  # noqa: N815
    headers: H
    body: B


class Request[B: ResponseBody, H: ResponseHeaders](BaseModel):
    @property
    def action(self) -> str:
        return type(self).__name__.removesuffix("Request")

    @classmethod
    def _find_model(cls) -> tuple[type[B], type[H]]:
        for c in cls.mro():
            match c:
                case type(__pydantic_generic_metadata__={"args": (_, _) as args}):
                    return tuple(args)
                case _:
                    pass

        raise TypeError(f"{cls} doesnt inherit from Request")

    @classmethod
    def parse_response(cls, response: dict[str, object]) -> Response[B, H]:
        body, headers = cls._find_model()
        return Response[body, headers].model_validate(response)


class InstanceStatus(str, enum.Enum):
    PENDING = "Pending"
    RUNNING = "Running"
    STARTING = "Starting"
    STOPPING = "Stopping"
    STOPPED = "Stopped"


class DescribeInstanceStatusResponseBody(Paginated, ResponseBody):
    class _InstanceStatuses(BaseModel):
        class _InstanceStatus(BaseModel):
            Status: InstanceStatus
            InstanceId: str

        InstanceStatus: list[_InstanceStatus]

    InstanceStatuses: _InstanceStatuses


class DescribeInstanceStatusRequest(
    Request[
        DescribeInstanceStatusResponseBody,
        ResponseHeaders,
    ]
):
    RegionId: str
    InstanceIds: list[str]


class RunInstancesResponseBody(ResponseBody):
    class _InstanceIdSets(BaseModel):
        InstanceIdSet: list[str]

    OrderId: str | None = None
    InstanceIdSets: _InstanceIdSets


class RunInstancesRequest(
    Request[
        RunInstancesResponseBody,
        ResponseHeaders,
    ]
):
    RegionId: str
    Amount: int
    LaunchTemplateId: str
    InstanceName: str


class InstanceInfo(BaseModel):
    class _IpAddress(BaseModel):
        IpAddress: list[str]

    class _EipAddress(BaseModel):
        AllocationId: str
        IpAddress: str
        InternetChargeType: str

    class _ImageOptions(BaseModel): ...

    class _Tags(BaseModel):
        class _TagKV(BaseModel):
            TagKey: str
            TagValue: str

        Tag: list[_TagKV]

    class _HibernationOptions(BaseModel):
        Configured: bool

    class _AdditionalInfo(BaseModel): ...

    class _MetadataOptions(BaseModel):
        HttpTokens: str
        HttpEndpoint: str

    class _CpuOptions(BaseModel):
        ThreadsPerCore: int
        Numa: str
        CoreCount: int

    class _PrivateDnsNameOptions(BaseModel): ...

    class _SecurityGroupIds(BaseModel):
        SecurityGroupId: list[str]

    class _VpcAttributes(BaseModel):
        class _IpAddress(BaseModel):
            IpAddress: list[str]

        PrivateIpAddress: _IpAddress
        VpcId: str
        VSwitchId: str
        NatIpAddress: str

    class _DedicatedInstanceAttribute(BaseModel):
        Tenancy: str
        Affinity: str

    class _NetworkInterfaces(BaseModel):
        class _NetworkInterface(BaseModel):
            Type: str
            PrimaryIpAddress: str
            MacAddress: str
            NetworkInterfaceId: str
            PrivateIpSets: dict[str, object]

        NetworkInterface: list[_NetworkInterface]

    class _EcsCapacityReservationAttr(BaseModel):
        CapacityReservationPreference: str
        CapacityReservationId: str

    class _DedicatedHostAttribute(BaseModel):
        DedicatedHostId: str
        DedicatedHostName: str
        DedicatedHostClusterId: str

    class _OperationLocks(BaseModel):
        class _LockReason(BaseModel):
            LockMsg: str
            LockReason: str

        LockReason: list[_LockReason]

    InstanceId: str
    ResourceGroupId: str
    Memory: int
    InstanceChargeType: str
    Cpu: int
    OSName: str
    InstanceNetworkType: str
    InnerIpAddress: _IpAddress
    ExpiredTime: str
    ImageId: str
    EipAddress: _EipAddress
    ImageOptions: _ImageOptions
    HostName: str
    Tags: _Tags
    VlanId: str
    Status: InstanceStatus
    HibernationOptions: _HibernationOptions
    AdditionalInfo: _AdditionalInfo
    MetadataOptions: _MetadataOptions
    StoppedMode: str
    CpuOptions: _CpuOptions
    StartTime: str
    PrivateDnsNameOptions: _PrivateDnsNameOptions
    DeletionProtection: bool
    SecurityGroupIds: _SecurityGroupIds
    VpcAttributes: _VpcAttributes
    InternetChargeType: str
    InstanceName: str
    SpotInterruptionBehavior: str
    DeploymentSetId: str
    InternetMaxBandwidthOut: int
    SerialNumber: str
    OSType: str
    CreationTime: str
    AutoReleaseTime: str
    Description: str
    InstanceTypeFamily: str
    DedicatedInstanceAttribute: _DedicatedInstanceAttribute
    SpotDuration: int
    PublicIpAddress: _IpAddress
    GPUSpec: str
    NetworkInterfaces: _NetworkInterfaces
    SpotPriceLimit: float
    DeviceAvailable: bool
    SaleCycle: str
    InstanceType: str
    SpotStrategy: str
    OSNameEn: str
    KeyPairName: str
    IoOptimized: bool
    ZoneId: str
    ClusterId: str
    EcsCapacityReservationAttr: _EcsCapacityReservationAttr
    DedicatedHostAttribute: _DedicatedHostAttribute
    GPUAmount: int
    OperationLocks: _OperationLocks
    InternetMaxBandwidthIn: int
    Recyclable: bool
    RegionId: str
    CreditSpecification: str


class DescribeInstancesResponseBody(Paginated, ResponseBody):
    class _Instances(BaseModel):
        Instance: list[InstanceInfo]

    Instances: _Instances


class DescribeInstancesRequest(
    Request[
        DescribeInstancesResponseBody,
        ResponseHeaders,
    ]
):
    RegionId: str
    InstanceIds: list[str] | None = None
    NextToken: str | None = None
    MaxResults: int = 1
