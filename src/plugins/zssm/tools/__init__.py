from collections.abc import AsyncIterator, Callable
from contextlib import AsyncExitStack, asynccontextmanager
from dataclasses import dataclass
from typing import Any

import anyio
import httpx

from src.service.llm import BoundTool, LLMService

from ..config import ZssmConfig
from ..contracts import (
    ParticipantResolver,
    ZssmInvocationFacts,
    ZssmToolContext,
)
from .chat_history import build_recent_messages_tool
from .participants import InvocationParticipantResolver, build_participant_info_tool
from .web import (
    HttpxSafePageFetcher,
    InvocationCitationRegistry,
    InvocationMediaRegistry,
    SourceImageToolContext,
    build_fetch_page_tool,
    build_source_image_tool,
    build_web_search_tool,
    create_web_search_provider,
    resolve_card_urls,
)


@dataclass(frozen=True, slots=True)
class ZssmToolResources:
    context: ZssmToolContext
    tools: tuple[BoundTool[Any, Any], ...]
    citations: InvocationCitationRegistry


@asynccontextmanager
async def open_zssm_tool_resources(
    *,
    config: ZssmConfig,
    session: Any,
    participant_resolver: ParticipantResolver,
    history_high_water: int,
    invocation: ZssmInvocationFacts,
    llm_service: LLMService,
    correlation_id: str | None = None,
    citation_registry_factory: Callable[
        [], InvocationCitationRegistry
    ] = InvocationCitationRegistry,
    page_fetcher_factory: Callable[..., HttpxSafePageFetcher] = HttpxSafePageFetcher,
) -> AsyncIterator[ZssmToolResources]:
    """Own every invocation-bound web resource and close it exactly once."""

    async with AsyncExitStack() as stack:
        citations = citation_registry_factory()
        media_registry = InvocationMediaRegistry()
        search_client: httpx.AsyncClient | None = None
        ddgs_limiter: anyio.CapacityLimiter | None = None
        if config.web_search.backend != "ddgs":
            search_client = await stack.enter_async_context(
                httpx.AsyncClient(
                    trust_env=False,
                    follow_redirects=False,
                    timeout=httpx.Timeout(None),
                )
            )
        if config.web_search.backend == "ddgs":
            ddgs_limiter = anyio.CapacityLimiter(config.web_search.ddgs_max_parallel)

        search_provider = create_web_search_provider(
            config.web_search,
            citations,
            client=search_client,
            ddgs_limiter=ddgs_limiter,
        )
        page_fetcher = page_fetcher_factory(
            config.fetch_page,
            citations,
            media_registry=media_registry,
        )
        await stack.enter_async_context(page_fetcher)
        context = ZssmToolContext(
            session=session,
            participant_resolver=participant_resolver,
            search_provider=search_provider,
            page_fetcher=page_fetcher,
            history_high_water=history_high_water,
            invocation=invocation,
            web_search_config=config.web_search,
            fetch_page_config=config.fetch_page,
            history_config=config.history,
            participants_config=config.participants,
            citation_registry=citations,
        )
        web_search = build_web_search_tool(context)
        fetch_page = build_fetch_page_tool(context)
        tools_list: list[BoundTool[Any, Any]] = [web_search, fetch_page]
        if config.source_images.enabled:
            tools_list.append(
                build_source_image_tool(
                    SourceImageToolContext(
                        media_registry=media_registry,
                        page_fetcher=page_fetcher,
                        images_config=config.images,
                        source_config=config.source_images,
                        llm_service=llm_service,
                        primary_model=invocation.active_model,
                        vision_model=config.vision_model,
                        correlation_id=correlation_id,
                    )
                )
            )
        tools_list.extend(
            (
                build_recent_messages_tool(context),
                build_participant_info_tool(context),
            )
        )
        tools = tuple(tools_list)
        yield ZssmToolResources(context=context, tools=tools, citations=citations)


__all__ = [
    "InvocationParticipantResolver",
    "ZssmToolResources",
    "open_zssm_tool_resources",
    "resolve_card_urls",
]
