from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager
from dataclasses import dataclass
from typing import Any

import httpx
from nonebot_plugin_uninfo import Session

from src.service.llm import BoundTool, LLMService

from ..config import ZssmConfig
from ..contracts.input import DeferredImageInput
from ..contracts.participants import ParticipantResolver
from ..contracts.run import ZssmInvocationFacts
from ..input import AdapterImageFetcher
from .chat_history import RecentMessagesToolContext, build_recent_messages_tool
from .message_images import (
    InvocationMessageImageRegistry,
    MessageImageToolContext,
    build_message_image_tool,
)
from .participants import (
    InvocationParticipantResolver,
    ParticipantInfoToolContext,
    build_participant_info_tool,
)
from .web import (
    FetchPageToolContext,
    HttpxSafePageFetcher,
    InvocationCitationRegistry,
    InvocationMediaRegistry,
    SourceImageToolContext,
    WebSearchToolContext,
    build_fetch_page_tool,
    build_source_image_tool,
    build_web_search_tool,
    create_web_search_provider,
    resolve_card_urls,
)


@dataclass(frozen=True, slots=True)
class ZssmToolResources:
    tools: tuple[BoundTool[Any, Any], ...]
    citations: InvocationCitationRegistry


@asynccontextmanager
async def open_zssm_tool_resources(
    *,
    config: ZssmConfig,
    session: Session,
    participant_resolver: ParticipantResolver,
    history_high_water: int,
    invocation: ZssmInvocationFacts,
    llm_service: LLMService,
    deferred_images: tuple[DeferredImageInput, ...],
    adapter_image_fetcher: AdapterImageFetcher | None,
) -> AsyncIterator[ZssmToolResources]:
    """Own every invocation-bound tool resource and close it exactly once."""

    async with AsyncExitStack() as stack:
        citations = InvocationCitationRegistry()
        media_registry = InvocationMediaRegistry()
        message_images = InvocationMessageImageRegistry(deferred_images)
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
        page_fetcher = HttpxSafePageFetcher(
            config.fetch_page,
            citations,
            media_registry=media_registry,
        )
        await stack.enter_async_context(page_fetcher)
        tools_list = [
            build_web_search_tool(
                WebSearchToolContext(
                    search_provider=search_provider,
                    web_search_config=config.web_search,
                    citation_registry=citations,
                )
            ),
            build_fetch_page_tool(
                FetchPageToolContext(
                    page_fetcher=page_fetcher,
                    citation_registry=citations,
                )
            ),
            build_recent_messages_tool(
                RecentMessagesToolContext(
                    session=session,
                    participant_resolver=participant_resolver,
                    message_images=message_images,
                    history_high_water=history_high_water,
                    invocation=invocation,
                    history_config=config.history,
                )
            ),
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
            build_participant_info_tool(
                ParticipantInfoToolContext(
                    participant_resolver=participant_resolver,
                    participants_config=config.participants,
                )
            ),
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
            tools=tuple(tools_list),
            citations=citations,
        )


__all__ = [
    "InvocationParticipantResolver",
    "ZssmToolResources",
    "open_zssm_tool_resources",
    "resolve_card_urls",
]
