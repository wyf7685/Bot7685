from typing import cast

from src.service.llm import JSONValue

from ...contracts.web import Citation, CitationRegistry, CitationSourceKind
from ...http_transport import normalize_http_url


class InvocationCitationRegistry(CitationRegistry):
    """Invocation-local stable citation allocation with normalized URL aliases."""

    def __init__(self) -> None:
        self._by_url: dict[str, str] = {}
        self._citations: dict[str, Citation] = {}
        self._allocation_order: list[str] = []
        self._used: set[str] = set()

    def register(
        self,
        *,
        source_kind: CitationSourceKind,
        title: str,
        url: str,
        source: str | None = None,
        published: str | None = None,
    ) -> Citation:
        normalized_url = normalize_http_url(url)
        if citation_id := self._by_url.get(normalized_url):
            existing = self._citations[citation_id]
            updated = _merge_citation(
                existing,
                source_kind=source_kind,
                title=title,
                url=normalized_url,
                source=source,
                published=published,
            )
            self._citations[citation_id] = updated
            return updated

        citation_id = f"s{len(self._allocation_order) + 1}"
        citation = Citation(
            citation_id=citation_id,
            source_kind=source_kind,
            title=title,
            url=normalized_url,
            source=source,
            published=published,
        )
        self._by_url[normalized_url] = citation_id
        self._citations[citation_id] = citation
        self._allocation_order.append(citation_id)
        return citation

    def register_page(
        self,
        *,
        requested_url: str,
        final_url: str,
        title: str,
        source: str | None = None,
        published: str | None = None,
    ) -> Citation:
        """Register a fetched page while reusing a prior search citation."""

        requested = normalize_http_url(requested_url)
        final = normalize_http_url(final_url)
        requested_id = self._by_url.get(requested)
        final_id = self._by_url.get(final)

        if requested_id is None and final_id is None:
            citation = self.register(
                source_kind=CitationSourceKind.PAGE,
                title=title,
                url=final,
                source=source,
                published=published,
            )
            self._by_url[requested] = citation.citation_id
            return citation

        citation_id = requested_id or cast("str", final_id)
        existing = self._citations[citation_id]
        citation_url = final if final_id in (None, citation_id) else requested
        updated = Citation(
            citation_id=citation_id,
            source_kind=CitationSourceKind.PAGE,
            title=title,
            url=citation_url,
            source=source or existing.source,
            published=published or existing.published,
        )
        self._citations[citation_id] = updated
        self._by_url[requested] = citation_id
        if final_id in (None, citation_id):
            self._by_url[final] = citation_id
        return updated

    def get(self, citation_id: str) -> Citation | None:
        return self._citations.get(citation_id)

    def mark_used(self, citation_id: str) -> bool:
        if citation_id not in self._citations:
            return False
        self._used.add(citation_id)
        return True

    def used_citations(self) -> tuple[Citation, ...]:
        return tuple(
            self._citations[citation_id]
            for citation_id in self._allocation_order
            if citation_id in self._used
        )


def _merge_citation(
    existing: Citation,
    *,
    source_kind: CitationSourceKind,
    title: str,
    url: str,
    source: str | None,
    published: str | None,
) -> Citation:
    if (
        source_kind is CitationSourceKind.PAGE
        or existing.source_kind is CitationSourceKind.PAGE
    ):
        use_new = source_kind is CitationSourceKind.PAGE
        return Citation(
            citation_id=existing.citation_id,
            source_kind=CitationSourceKind.PAGE,
            title=title if use_new else existing.title,
            url=url,
            source=(source if use_new else existing.source)
            or existing.source
            or source,
            published=(published if use_new else existing.published)
            or existing.published
            or published,
        )
    return Citation(
        citation_id=existing.citation_id,
        source_kind=existing.source_kind,
        title=existing.title,
        url=existing.url,
        source=existing.source or source,
        published=existing.published or published,
    )


def citation_json(citation: Citation) -> dict[str, JSONValue]:
    return {
        "citation_id": citation.citation_id,
        "source_kind": citation.source_kind.value,
        "title": citation.title,
        "url": citation.url,
        "source": citation.source,
        "published": citation.published,
    }


__all__ = ["InvocationCitationRegistry", "citation_json"]
