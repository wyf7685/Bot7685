import re
from typing import Any

_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def normalize_page_text(value: str) -> str:
    value = _CONTROL_RE.sub("", value.replace("\r\n", "\n").replace("\r", "\n"))
    lines = [line.rstrip() for line in value.split("\n")]
    normalized: list[str] = []
    blank = False
    for line in lines:
        if line.strip():
            normalized.append(line)
            blank = False
        elif normalized and not blank:
            normalized.append("")
            blank = True
    while normalized and not normalized[-1]:
        normalized.pop()
    return "\n".join(normalized).strip()


def normalize_single_line(value: str, maximum: int) -> str:
    value = _CONTROL_RE.sub("", value)
    value = " ".join(value.split())
    return value[:maximum].strip()


def optional_metadata(value: Any, maximum: int) -> str | None:
    if not isinstance(value, str):
        return None
    return normalize_single_line(value, maximum) or None


__all__ = ["normalize_page_text", "normalize_single_line", "optional_metadata"]
