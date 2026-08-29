from dataclasses import dataclass, field

from pydantic import BaseModel, ConfigDict, Field, create_model, field_validator

from src.service.llm import BoundTool, JSONValue, ToolOutput

from ....config import WebSearchConfig
from ....contracts._validation import _nonempty
from ....contracts.web import (
    CitationRegistry,
    SearchFreshness,
    SearchResult,
    WebSearchProvider,
)
from ..citations import citation_json
from .common import WebSearchError


class WebSearchArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    query: str = Field(min_length=1, max_length=300)
    max_results: int = Field(default=5, ge=1, le=8)
    freshness: SearchFreshness = "any"

    @field_validator("query")
    @classmethod
    def validate_query(cls, value: str) -> str:
        return _nonempty(value, "query")


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


@dataclass(frozen=True, slots=True)
class WebSearchToolContext:
    search_provider: WebSearchProvider = field(repr=False, compare=False)
    web_search_config: WebSearchConfig
    citation_registry: CitationRegistry = field(repr=False, compare=False)


def build_web_search_tool(
    context: WebSearchToolContext,
) -> BoundTool[WebSearchToolContext, WebSearchArgs]:
    """Bind the configured web search provider to one invocation context."""

    return BoundTool(
        name="web_search",
        description=(
            "Search the configured web provider. Results include stable "
            "citation IDs that should be referenced when used in the answer."
        ),
        arguments_type=bind_web_search_args(context.web_search_config),
        context=context,
        handler=_handle_web_search,
    )


async def _handle_web_search(
    context: WebSearchToolContext,
    arguments: WebSearchArgs,
) -> ToolOutput:
    try:
        result = await context.search_provider.search(
            query=arguments.query,
            max_results=arguments.max_results,
            freshness=arguments.freshness,
        )
    except WebSearchError as error:
        backend = context.web_search_config.backend
        diagnostic_parts = [f"backend={backend}"]
        if backend == "ddgs":
            diagnostic_parts.append(f"engine={context.web_search_config.ddgs_backend}")
        if error.status_code is not None:
            diagnostic_parts.append(f"status={error.status_code}")
        if error.cause_type is not None:
            diagnostic_parts.append(f"cause={error.cause_type}")
        if error.reason is not None:
            diagnostic_parts.append(f"reason={error.reason}")
        return ToolOutput(
            value={"status": "error", "error": {"code": error.code}},
            summary="web_search status=error results=0 truncated=false",
            reported_error_code=f"web_search_{error.code}",
            diagnostic=" ".join(diagnostic_parts),
        )

    citations: list[JSONValue] = []
    for item in result.results:
        citation = context.citation_registry.get(item.citation_id)
        if citation is None:
            raise RuntimeError("search provider returned an unknown citation")
        citations.append(citation_json(citation))
    results: list[JSONValue] = [_search_result_json(item) for item in result.results]
    value: dict[str, JSONValue] = {
        "status": "ok",
        "query": result.query,
        "results": results,
        "truncated": result.truncated,
        "citations": citations,
    }
    output = ToolOutput(
        value=value,
        summary=(
            f"web_search status=ok results={result.returned} "
            f"truncated={str(result.truncated).lower()}"
        ),
    )
    for item in result.results:
        context.citation_registry.mark_used(item.citation_id)
    return output


def _search_result_json(result: SearchResult) -> dict[str, JSONValue]:
    return {
        "rank": result.rank,
        "title": result.title,
        "url": result.url,
        "snippet": result.snippet,
        "source": result.source,
        "published": result.published,
        "language": result.language,
        "citation_id": result.citation_id,
    }


__all__ = ["WebSearchToolContext", "build_web_search_tool"]
