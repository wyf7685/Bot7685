import anyio
import httpx

from ....config import WebSearchConfig
from ....contracts import CitationRegistry, WebSearchProvider
from .brave import BraveSearchProvider
from .ddgs import DDGSSearchProvider
from .tavily import TavilySearchProvider


def create_web_search_provider(
    config: WebSearchConfig,
    citation_registry: CitationRegistry,
    *,
    client: httpx.AsyncClient | None = None,
    ddgs_limiter: anyio.CapacityLimiter | None = None,
) -> WebSearchProvider:
    """Create exactly the configured provider; never fall back to another backend."""

    if config.backend == "brave":
        if client is None:
            raise ValueError("a shared HTTP client is required for Brave search")
        return BraveSearchProvider(config, citation_registry, client)
    if config.backend == "tavily":
        if client is None:
            raise ValueError("a shared HTTP client is required for Tavily search")
        return TavilySearchProvider(config, citation_registry, client)
    if config.backend == "ddgs":
        return DDGSSearchProvider(config, citation_registry, limiter=ddgs_limiter)
    raise ValueError("unsupported web search backend")


__all__ = ["create_web_search_provider"]
