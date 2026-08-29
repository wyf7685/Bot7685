import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Annotated, Literal, Protocol
from urllib.parse import urlsplit

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    create_model,
    field_validator,
)

from .config import FetchPageConfig, HistoryConfig, ParticipantsConfig, WebSearchConfig

if TYPE_CHECKING:
    from nonebot_plugin_alconna import Image, UniMessage
    from nonebot_plugin_uninfo import Session

    from src.service.llm import ChatInputPart, ImagePart, TokenUsage

_PARTICIPANT_ALIAS_PATTERN = r"p_[0-9a-f]{16}"
_PARTICIPANT_ALIAS_RE = re.compile(rf"^{_PARTICIPANT_ALIAS_PATTERN}$")
_CITATION_ID_RE = re.compile(r"^s[1-9][0-9]*$")
_IMAGE_LABEL_RE = re.compile(r"^image-[1-9][0-9]*$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_MEDIA_ID_RE = re.compile(r"^m[1-9][0-9]*$")


def _nonempty(value: str, field_name: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError(f"{field_name} must not be empty")
    return value


def _participant_alias(value: str) -> str:
    if not _PARTICIPANT_ALIAS_RE.fullmatch(value):
        raise ValueError("participant alias must match p_<16 lowercase hex characters>")
    return value


def _citation_id(value: str) -> str:
    if not _CITATION_ID_RE.fullmatch(value):
        raise ValueError("citation_id must match s<positive integer>")
    return value


def _image_label(value: str) -> str:
    if not _IMAGE_LABEL_RE.fullmatch(value):
        raise ValueError("image label must match image-<positive integer>")
    return value


def _sha256(value: str) -> str:
    value = value.lower()
    if not _SHA256_RE.fullmatch(value):
        raise ValueError("sha256 must contain 64 hexadecimal characters")
    return value


def _http_url(value: str, field_name: str) -> str:
    value = _nonempty(value, field_name)
    if any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise ValueError(f"{field_name} must not contain control characters")
    try:
        parsed = urlsplit(value)
        _ = parsed.port
    except ValueError as error:
        raise ValueError(f"{field_name} is not a valid HTTP URL") from error
    if parsed.scheme.lower() not in {"http", "https"} or parsed.hostname is None:
        raise ValueError(f"{field_name} must be an absolute HTTP(S) URL")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError(f"{field_name} must not contain user information")
    return value


def _aware(value: datetime, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value


class InputLocation(StrEnum):
    QUOTED = "quoted"
    CURRENT = "current"


@dataclass(frozen=True, slots=True)
class CollectedImageInput:
    label: str
    location: InputLocation
    source_index: int
    segment: Image = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "label", _image_label(self.label))
        if self.source_index < 0:
            raise ValueError("source_index must not be negative")


@dataclass(frozen=True, slots=True)
class CollectedInput:
    """A copied run snapshot; aliases alone never make an invocation nonempty."""

    prompt_text: str
    prompt_parts: tuple[ChatInputPart, ...]
    current: UniMessage = field(repr=False, compare=False)
    quoted: UniMessage | None = field(default=None, repr=False, compare=False)
    images: tuple[CollectedImageInput, ...] = ()
    omitted_images: int = 0
    participant_aliases: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "prompt_parts", tuple(self.prompt_parts))
        object.__setattr__(self, "images", tuple(self.images))
        if self.omitted_images < 0:
            raise ValueError("omitted image count must not be negative")
        object.__setattr__(self, "participant_aliases", tuple(self.participant_aliases))
        object.__setattr__(self, "current", self.current.copy())
        if self.quoted is not None:
            object.__setattr__(self, "quoted", self.quoted.copy())
        indices = tuple(image.source_index for image in self.images)
        if indices != tuple(sorted(indices)):
            raise ValueError("images must retain source order")
        labels = tuple(image.label for image in self.images)
        if labels != tuple(f"image-{i}" for i in range(1, len(labels) + 1)):
            raise ValueError("images must use contiguous stable labels")
        for alias in self.participant_aliases:
            _participant_alias(alias)
        if len(set(self.participant_aliases)) != len(self.participant_aliases):
            raise ValueError("participant_aliases must be unique")
        if self.is_empty:
            raise ValueError(
                "collected input must contain text, prompt parts, or images"
            )

    @property
    def is_empty(self) -> bool:
        return (
            not self.prompt_text.strip() and not self.prompt_parts and not self.images
        )


@dataclass(frozen=True, slots=True)
class NormalizedImage:
    label: str
    jpeg_bytes: bytes = field(repr=False)
    source_bytes: int
    width: int
    height: int
    sha256: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "label", _image_label(self.label))
        object.__setattr__(self, "sha256", _sha256(self.sha256))
        if not self.jpeg_bytes or self.source_bytes <= 0:
            raise ValueError("normalized image byte counts must be positive")
        if self.width <= 0 or self.height <= 0:
            raise ValueError("normalized image dimensions must be positive")


@dataclass(frozen=True, slots=True)
class PreparedImage:
    label: str
    part: ImagePart = field(repr=False)
    payload_bytes: int
    width: int
    height: int
    sha256: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "label", _image_label(self.label))
        object.__setattr__(self, "sha256", _sha256(self.sha256))
        if self.payload_bytes <= 0 or self.width <= 0 or self.height <= 0:
            raise ValueError("prepared image sizes must be positive")


class ImageFailureStage(StrEnum):
    ACQUISITION = "acquisition"
    NORMALIZATION = "normalization"
    VISION = "vision"


class ImageFailureCategory(StrEnum):
    UNAVAILABLE = "unavailable"
    TOO_LARGE = "too_large"
    INVALID = "invalid"
    DOWNLOAD = "download"
    PROCESSING = "processing"
    MODEL = "model"


@dataclass(frozen=True, slots=True)
class ImageFailure:
    label: str
    stage: ImageFailureStage
    category: ImageFailureCategory

    def __post_init__(self) -> None:
        object.__setattr__(self, "label", _image_label(self.label))


@dataclass(frozen=True, slots=True)
class VisionObservation:
    label: str
    text: str
    truncated: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "label", _image_label(self.label))
        object.__setattr__(self, "text", _nonempty(self.text, "vision observation"))


@dataclass(frozen=True, slots=True)
class VisionStageResult:
    model_alias: str
    model_id: str
    observations: tuple[VisionObservation, ...]
    failures: tuple[ImageFailure, ...]
    usage: TokenUsage
    elapsed: float

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "model_alias", _nonempty(self.model_alias, "model_alias")
        )
        object.__setattr__(self, "model_id", _nonempty(self.model_id, "model_id"))
        object.__setattr__(self, "observations", tuple(self.observations))
        object.__setattr__(self, "failures", tuple(self.failures))
        if self.elapsed < 0:
            raise ValueError("elapsed must not be negative")
        labels = [item.label for item in (*self.observations, *self.failures)]
        if not labels or len(set(labels)) != len(labels):
            raise ValueError("each image must have exactly one vision outcome")

    @property
    def partial_success(self) -> bool:
        return bool(self.observations and self.failures)


@dataclass(frozen=True, slots=True)
class ImageStageStatistics:
    requested: int = 0
    unique: int = 0
    prepared: int = 0
    acquisition_failed: int = 0
    normalization_failed: int = 0
    vision_succeeded: int = 0
    vision_failed: int = 0
    vision_truncated: int = 0

    def __post_init__(self) -> None:
        values = tuple(getattr(self, name) for name in self.__slots__)
        if any(value < 0 for value in values):
            raise ValueError("image statistics must not be negative")
        if self.unique > self.requested:
            raise ValueError("unique images must not exceed requested images")
        if self.prepared + self.preparation_failed != self.unique:
            raise ValueError("every unique image must be prepared or fail preparation")
        if self.vision_succeeded + self.vision_failed > self.prepared:
            raise ValueError("vision outcomes must not exceed prepared images")
        if self.vision_truncated > self.vision_succeeded:
            raise ValueError("truncated observations must have succeeded")

    @property
    def preparation_failed(self) -> int:
        return self.acquisition_failed + self.normalization_failed

    @property
    def partial_success(self) -> bool:
        vision_attempted = self.vision_succeeded + self.vision_failed > 0
        usable_successes = self.vision_succeeded if vision_attempted else self.prepared
        failures = self.preparation_failed + self.vision_failed
        return usable_successes > 0 and failures > 0


class ParticipantRole(StrEnum):
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"
    UNKNOWN = "unknown"


class ParticipantMetadataStatus(StrEnum):
    FULL = "full"
    PARTIAL = "partial"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class ParticipantRef:
    participant_alias: str
    raw_user_id: str = field(repr=False)
    is_invoker: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "participant_alias", _participant_alias(self.participant_alias)
        )
        if not self.raw_user_id:
            raise ValueError("raw_user_id must not be empty")


@dataclass(frozen=True, slots=True)
class ParticipantInfo:
    """The complete model-facing allowlist; deliberately contains no raw ID field."""

    participant_alias: str
    display_name: str
    scene_nickname: str | None
    account_name: str | None
    role: ParticipantRole
    is_invoker: bool
    metadata_status: ParticipantMetadataStatus

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "participant_alias", _participant_alias(self.participant_alias)
        )
        object.__setattr__(
            self, "display_name", _nonempty(self.display_name, "display_name")
        )
        for name in ("scene_nickname", "account_name"):
            if (value := getattr(self, name)) is not None:
                object.__setattr__(self, name, _nonempty(value, name))


class ParticipantResolver(Protocol):
    def observe(
        self, raw_user_id: str, *, is_invoker: bool = False
    ) -> ParticipantRef: ...
    def alias_for(self, raw_user_id: str) -> str | None: ...
    def ref_for_alias(self, participant_alias: str) -> ParticipantRef | None: ...
    async def resolve_known(
        self, participant_aliases: Sequence[str]
    ) -> tuple[ParticipantInfo, ...]: ...


class CitationSourceKind(StrEnum):
    SEARCH = "search"
    PAGE = "page"


@dataclass(frozen=True, slots=True)
class Citation:
    citation_id: str
    source_kind: CitationSourceKind
    title: str
    url: str
    source: str | None = None
    published: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "citation_id", _citation_id(self.citation_id))
        object.__setattr__(self, "title", _nonempty(self.title, "title"))
        object.__setattr__(self, "url", _http_url(self.url, "url"))
        for name in ("source", "published"):
            if (value := getattr(self, name)) is not None:
                object.__setattr__(self, name, _nonempty(value, name))


class CitationRegistry(Protocol):
    """register deduplicates normalized targets and allocates stable s1... IDs."""

    def register(
        self,
        *,
        source_kind: CitationSourceKind,
        title: str,
        url: str,
        source: str | None = None,
        published: str | None = None,
    ) -> Citation: ...
    def get(self, citation_id: str) -> Citation | None: ...
    def mark_used(self, citation_id: str) -> bool: ...
    def used_citations(self) -> tuple[Citation, ...]: ...


@dataclass(frozen=True, slots=True)
class SearchResult:
    rank: int
    title: str
    url: str
    snippet: str
    source: str | None
    published: str | None
    language: str | None
    citation_id: str

    def __post_init__(self) -> None:
        if self.rank <= 0:
            raise ValueError("rank must be positive")
        object.__setattr__(self, "title", _nonempty(self.title, "title"))
        object.__setattr__(self, "url", _http_url(self.url, "url"))
        object.__setattr__(self, "snippet", self.snippet.strip())
        object.__setattr__(self, "citation_id", _citation_id(self.citation_id))
        for name in ("source", "published", "language"):
            if (value := getattr(self, name)) is not None:
                object.__setattr__(self, name, _nonempty(value, name))


@dataclass(frozen=True, slots=True)
class WebSearchResult:
    query: str
    results: tuple[SearchResult, ...]
    truncated: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "query", _nonempty(self.query, "query"))
        object.__setattr__(self, "results", tuple(self.results))
        if tuple(item.rank for item in self.results) != tuple(
            range(1, len(self.results) + 1)
        ):
            raise ValueError("search result ranks must be contiguous and ordered")
        ids = tuple(item.citation_id for item in self.results)
        if len(set(ids)) != len(ids):
            raise ValueError("search results must not repeat citation IDs")

    @property
    def returned(self) -> int:
        return len(self.results)


@dataclass(frozen=True, slots=True)
class MediaSetRef:
    media_id: str
    count: int
    restricted: bool = False

    def __post_init__(self) -> None:
        media_id = self.media_id.strip()
        if not _MEDIA_ID_RE.fullmatch(media_id):
            raise ValueError("media_id must match m<positive integer>")
        if self.count <= 0:
            raise ValueError("media count must be positive")
        object.__setattr__(self, "media_id", media_id)


@dataclass(frozen=True, slots=True)
class WebPageResult:
    title: str
    author: str | None
    site: str | None
    published: str | None
    language: str | None
    text: str
    truncated: bool
    final_url: str
    content_sha256: str
    citation_id: str
    media: MediaSetRef | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "title", _nonempty(self.title, "title"))
        object.__setattr__(self, "text", _nonempty(self.text, "text"))
        object.__setattr__(self, "final_url", _http_url(self.final_url, "final_url"))
        object.__setattr__(self, "content_sha256", _sha256(self.content_sha256))
        object.__setattr__(self, "citation_id", _citation_id(self.citation_id))
        if self.media is not None and not isinstance(self.media, MediaSetRef):
            raise TypeError("page media must be a MediaSetRef")
        for name in ("author", "site", "published", "language"):
            if (value := getattr(self, name)) is not None:
                object.__setattr__(self, name, _nonempty(value, name))


SearchFreshness = Literal["any", "day", "week", "month", "year"]


class WebSearchProvider(Protocol):
    """A configured invocation-bound provider; credentials remain inside it."""

    async def search(
        self,
        *,
        query: str,
        max_results: int,
        freshness: SearchFreshness,
    ) -> WebSearchResult: ...


class SafePageFetcher(Protocol):
    """An invocation-bound SSRF-safe fetcher with policy already configured."""

    async def fetch(self, url: str) -> WebPageResult: ...


@dataclass(frozen=True, slots=True)
class HistoryMessage:
    timestamp: str
    participant_alias: str
    content: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "timestamp", _nonempty(self.timestamp, "timestamp"))
        object.__setattr__(
            self, "participant_alias", _participant_alias(self.participant_alias)
        )
        object.__setattr__(self, "content", _nonempty(self.content, "content"))


class HistoryStatus(StrEnum):
    AVAILABLE = "available"
    UNAVAILABLE = "history_unavailable"


@dataclass(frozen=True, slots=True)
class RecentMessagesResult:
    status: HistoryStatus
    messages: tuple[HistoryMessage, ...] = ()
    truncated: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "messages", tuple(self.messages))
        if self.status is HistoryStatus.UNAVAILABLE and self.messages:
            raise ValueError("unavailable history must not contain messages")

    @property
    def returned(self) -> int:
        return len(self.messages)


class _StrictToolArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class WebSearchArgs(_StrictToolArgs):
    query: str = Field(min_length=1, max_length=300)
    max_results: int = Field(default=5, ge=1, le=8)
    freshness: SearchFreshness = "any"

    @field_validator("query")
    @classmethod
    def validate_query(cls, value: str) -> str:
        return _nonempty(value, "query")


class FetchPageArgs(_StrictToolArgs):
    url: str = Field(min_length=1)

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        return _nonempty(value, "url")


class RecentMessagesArgs(_StrictToolArgs):
    """Absolute safety bounds used as the base for a config-bound schema.

    ``bind_recent_messages_args`` must be used for ``BoundTool`` so model-visible
    defaults and effective limits come from the run's ``HistoryConfig``.
    """

    count: int = Field(ge=1, le=50)
    lookback_minutes: int = Field(ge=1, le=1440)
    search_text: str | None = Field(default=None, max_length=128)


ParticipantAlias = Annotated[
    str, StringConstraints(pattern=rf"^{_PARTICIPANT_ALIAS_PATTERN}$")
]


class ParticipantInfoArgs(_StrictToolArgs):
    participant_aliases: list[ParticipantAlias] = Field(min_length=1, max_length=20)


def bind_web_search_args(config: WebSearchConfig) -> type[WebSearchArgs]:
    """Materialize the strict model schema for one configured search provider."""

    maximum = min(8, config.max_results)
    return create_model(
        f"ConfiguredWebSearchArgsMax{maximum}",
        __base__=WebSearchArgs,
        __module__=__name__,
        max_results=(
            int,
            Field(default=min(5, maximum), ge=1, le=maximum),
        ),
    )


def bind_recent_messages_args(config: HistoryConfig) -> type[RecentMessagesArgs]:
    """Materialize strict defaults and effective caps from history config."""

    count_maximum = min(50, config.max_count)
    lookback_maximum = min(1440, config.max_lookback_minutes)
    search_maximum = min(128, config.max_search_chars)
    return create_model(
        (
            "ConfiguredRecentMessagesArgs"
            f"C{count_maximum}L{lookback_maximum}S{search_maximum}"
        ),
        __base__=RecentMessagesArgs,
        __module__=__name__,
        count=(
            int,
            Field(default=config.default_count, ge=1, le=count_maximum),
        ),
        lookback_minutes=(
            int,
            Field(
                default=config.default_lookback_minutes,
                ge=1,
                le=lookback_maximum,
            ),
        ),
        search_text=(
            str | None,
            Field(default=None, max_length=search_maximum),
        ),
    )


def bind_participant_info_args(
    config: ParticipantsConfig,
) -> type[ParticipantInfoArgs]:
    """Materialize the strict alias-list cap for one invocation."""

    maximum = min(20, config.max_per_tool_call)
    return create_model(
        f"ConfiguredParticipantInfoArgsMax{maximum}",
        __base__=ParticipantInfoArgs,
        __module__=__name__,
        participant_aliases=(
            list[ParticipantAlias],
            Field(min_length=1, max_length=maximum),
        ),
    )


@dataclass(frozen=True, slots=True)
class ZssmInvocationFacts:
    started_at: datetime
    active_model: str
    invoker_alias: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "started_at", _aware(self.started_at, "started_at"))
        object.__setattr__(
            self, "active_model", _nonempty(self.active_model, "active_model")
        )
        object.__setattr__(
            self, "invoker_alias", _participant_alias(self.invoker_alias)
        )


@dataclass(frozen=True, slots=True)
class ZssmToolContext:
    session: Session = field(repr=False, compare=False)
    participant_resolver: ParticipantResolver = field(repr=False, compare=False)
    search_provider: WebSearchProvider = field(repr=False, compare=False)
    page_fetcher: SafePageFetcher = field(repr=False, compare=False)
    history_high_water: int
    invocation: ZssmInvocationFacts
    web_search_config: WebSearchConfig
    fetch_page_config: FetchPageConfig
    history_config: HistoryConfig
    participants_config: ParticipantsConfig
    citation_registry: CitationRegistry = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        if self.history_high_water < 0:
            raise ValueError("history_high_water must not be negative")


class ToolDisplayStatus(StrEnum):
    SUCCESS = "success"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class ToolDisplayEntry:
    name: str
    summary: str
    status: ToolDisplayStatus
    elapsed: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _nonempty(self.name, "tool name"))
        summary = _nonempty(self.summary, "tool summary")
        if len(summary) > 160 or "\n" in summary or "\r" in summary:
            raise ValueError(
                "tool summary must be a single line of at most 160 characters"
            )
        object.__setattr__(self, "summary", summary)
        if self.elapsed < 0:
            raise ValueError("elapsed must not be negative")


@dataclass(frozen=True, slots=True)
class SourceEntry:
    citation_id: str
    title: str
    url: str
    source: str | None = None
    published: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "citation_id", _citation_id(self.citation_id))
        object.__setattr__(self, "title", _nonempty(self.title, "title"))
        object.__setattr__(self, "url", _http_url(self.url, "url"))
        for name in ("source", "published"):
            if (value := getattr(self, name)) is not None:
                object.__setattr__(self, name, _nonempty(value, name))

    @classmethod
    def from_citation(cls, citation: Citation) -> SourceEntry:
        return cls(
            citation.citation_id,
            citation.title,
            citation.url,
            citation.source,
            citation.published,
        )


@dataclass(frozen=True, slots=True)
class ModelStageUsage:
    model_alias: str
    model_id: str
    calls: int
    usage: TokenUsage
    elapsed: float

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "model_alias", _nonempty(self.model_alias, "model_alias")
        )
        object.__setattr__(self, "model_id", _nonempty(self.model_id, "model_id"))
        if self.calls < 0 or self.elapsed < 0:
            raise ValueError("stage calls and elapsed must not be negative")


@dataclass(frozen=True, slots=True)
class RunStatistics:
    total_elapsed: float
    primary_usage: ModelStageUsage
    vision_usage: ModelStageUsage | None
    images: ImageStageStatistics
    tool_calls: int
    tool_failures: int
    tool_elapsed: float
    tool_images: int = 0
    tool_image_bytes: int = 0

    def __post_init__(self) -> None:
        if self.total_elapsed < 0 or self.tool_elapsed < 0:
            raise ValueError("elapsed values must not be negative")
        if self.tool_calls < 0 or not 0 <= self.tool_failures <= self.tool_calls:
            raise ValueError("tool counts are inconsistent")
        if self.tool_images < 0 or self.tool_image_bytes < 0:
            raise ValueError("tool image statistics must not be negative")


class RenderFailureCategory(StrEnum):
    CONFIGURATION = "configuration"
    PERMISSION = "permission"
    EMPTY_INPUT = "empty_input"
    UNSUPPORTED_INPUT = "unsupported_input"
    FORWARD = "forward"
    IMAGE = "image"
    LIMITS = "limits"
    PROVIDER = "provider"
    TOOL = "tool"
    RENDER = "render"


@dataclass(frozen=True, slots=True)
class RenderFailure:
    category: RenderFailureCategory
    message: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "message", _nonempty(self.message, "failure message"))


@dataclass(frozen=True, slots=True)
class RenderModel:
    answer: str | None
    current: UniMessage = field(repr=False, compare=False)
    quoted: UniMessage | None = field(default=None, repr=False, compare=False)
    sources: tuple[SourceEntry, ...] = ()
    trace: tuple[ToolDisplayEntry, ...] = ()
    stats: RunStatistics | None = None
    failure: RenderFailure | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "current", self.current.copy())
        if self.quoted is not None:
            object.__setattr__(self, "quoted", self.quoted.copy())
        object.__setattr__(self, "sources", tuple(self.sources))
        object.__setattr__(self, "trace", tuple(self.trace))
        if (self.answer is None) == (self.failure is None):
            raise ValueError("render model requires exactly one of answer or failure")
        if self.answer is not None:
            object.__setattr__(self, "answer", _nonempty(self.answer, "answer"))
            if self.stats is None:
                raise ValueError("successful render model requires statistics")
        ids = tuple(source.citation_id for source in self.sources)
        if len(set(ids)) != len(ids):
            raise ValueError("render sources must not repeat citation IDs")
        if self.stats is not None and self.stats.tool_calls != len(self.trace):
            raise ValueError("tool trace length must match statistics.tool_calls")


__all__ = [
    "Citation",
    "CitationRegistry",
    "CitationSourceKind",
    "CollectedImageInput",
    "CollectedInput",
    "FetchPageArgs",
    "HistoryMessage",
    "HistoryStatus",
    "ImageFailure",
    "ImageFailureCategory",
    "ImageFailureStage",
    "ImageStageStatistics",
    "InputLocation",
    "MediaSetRef",
    "ModelStageUsage",
    "NormalizedImage",
    "ParticipantAlias",
    "ParticipantInfo",
    "ParticipantInfoArgs",
    "ParticipantMetadataStatus",
    "ParticipantRef",
    "ParticipantResolver",
    "ParticipantRole",
    "PreparedImage",
    "RecentMessagesArgs",
    "RecentMessagesResult",
    "RenderFailure",
    "RenderFailureCategory",
    "RenderModel",
    "RunStatistics",
    "SafePageFetcher",
    "SearchFreshness",
    "SearchResult",
    "SourceEntry",
    "ToolDisplayEntry",
    "ToolDisplayStatus",
    "VisionObservation",
    "VisionStageResult",
    "WebPageResult",
    "WebSearchArgs",
    "WebSearchProvider",
    "WebSearchResult",
    "ZssmInvocationFacts",
    "ZssmToolContext",
    "bind_participant_info_args",
    "bind_recent_messages_args",
    "bind_web_search_args",
]
