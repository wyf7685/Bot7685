from collections.abc import AsyncIterator, Callable
from contextlib import AsyncExitStack, asynccontextmanager
from dataclasses import dataclass
from typing import Any

import httpx

from src.service.llm import BoundTool, LLMService

from ..config import ZssmConfig
from ..contracts import (
    DeferredImageInput,
    ParticipantResolver,
    ZssmInvocationFacts,
    ZssmToolContext,
)
from ..input import AdapterImageFetcher
from .chat_history import build_recent_messages_tool
from .message_images import (
    InvocationMessageImageRegistry,
    MessageImageToolContext,
    build_message_image_tool,
)
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
    deferred_images: tuple[DeferredImageInput, ...],
    adapter_image_fetcher: AdapterImageFetcher | None,
    citation_registry_factory: Callable[
        [], InvocationCitationRegistry
    ] = InvocationCitationRegistry,
    page_fetcher_factory: Callable[..., HttpxSafePageFetcher] = HttpxSafePageFetcher,
    message_image_registry_factory: Callable[
        ..., InvocationMessageImageRegistry
    ] = InvocationMessageImageRegistry,
) -> AsyncIterator[ZssmToolResources]:
    """Own every invocation-bound tool resource and close it exactly once."""

    async with AsyncExitStack() as stack:
        citations = citation_registry_factory()
        media_registry = InvocationMediaRegistry()
        message_images = message_image_registry_factory(deferred_images)
        search_client: httpx.AsyncClient | None = None
        if config.web_search.backend != "ddgs":
            search_client = await stack.enter_async_context(
                httpx.AsyncClient(
                    trust_env=False,
                    follow_redirects=False,
                    timeout=httpx.Timeout(None),
                )
            )

        search_provider = create_web_search_provider(
            config.web_search,
            citations,
            client=search_client,
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
            message_images=message_images,
            history_high_water=history_high_water,
            invocation=invocation,
            web_search_config=config.web_search,
            fetch_page_config=config.fetch_page,
            history_config=config.history,
            participants_config=config.participants,
            citation_registry=citations,
        )
        tools_list = [
            build_web_search_tool(context),
            build_fetch_page_tool(context),
            build_recent_messages_tool(context),
            build_message_image_tool(
                MessageImageToolContext(
                    registry=message_images,
                    images_config=config.images,
                    llm_service=llm_service,
                    primary_model=invocation.active_model,
                    vision_model=config.vision_model,
                    adapter_image_fetcher=adapter_image_fetcher,
                )
            ),
            build_participant_info_tool(context),
        ]
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
                    )
                )
            )
        yield ZssmToolResources(
            context=context,
            tools=tuple(tools_list),
            citations=citations,
        )


__all__ = [
    "InvocationParticipantResolver",
    "ZssmToolResources",
    "open_zssm_tool_resources",
    "resolve_card_urls",
]
