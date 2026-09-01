import re
from collections.abc import Callable, Iterator

_CITATION_MARKER_RE = re.compile(r"\[(s[1-9][0-9]*(?:\s*[,，]\s*s[1-9][0-9]*)*)\]")
_CITATION_ID_RE = re.compile(r"s[1-9][0-9]*")


def iter_citation_ids(text: str) -> Iterator[str]:
    for marker in _CITATION_MARKER_RE.finditer(text):
        yield from _CITATION_ID_RE.findall(marker.group(1))


def normalize_citation_markers(
    text: str,
    lookup: Callable[[str], object | None],
) -> str:
    def replace(match: re.Match[str]) -> str:
        return "".join(
            f"[{citation_id}]"
            for citation_id in _CITATION_ID_RE.findall(match.group(1))
            if lookup(citation_id) is not None
        )

    return _CITATION_MARKER_RE.sub(replace, text)


__all__ = ["iter_citation_ids", "normalize_citation_markers"]
