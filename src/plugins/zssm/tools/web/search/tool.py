from src.service.llm import BoundTool, JSONValue, ToolOutput

from ....contracts import (
    SearchResult,
    WebSearchArgs,
    ZssmToolContext,
    bind_web_search_args,
)
from ..citations import citation_json
from .common import WebSearchError


def build_web_search_tool(
    context: ZssmToolContext,
) -> BoundTool[ZssmToolContext, WebSearchArgs]:
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
    context: ZssmToolContext,
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


__all__ = ["build_web_search_tool"]
