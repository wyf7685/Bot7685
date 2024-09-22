from typing import Any

from nonebot.utils import escape_tag


def color_repr(value: Any, /, *color: str) -> str:
    text = escape_tag(repr(value))
    for c in reversed(color):
        text = f"<{c}>{text}</{c}>"
    return text


def highlight_list(data: list[Any]) -> str:
    result = []
    for item in data:
        if isinstance(item, dict):
            result.append(highlight_dict(item))
        elif isinstance(item, list):
            result.append(highlight_list(item))
        else:
            result.append(escape_tag(repr(item)))
    return "[" + ", ".join(result) + "]"


def highlight_dict(data: dict[str, Any]) -> str:
    result = []
    for key, value in data.items():
        if isinstance(value, dict):
            text = highlight_dict(value)
        elif isinstance(value, list):
            text = highlight_list(value)
        else:
            text = escape_tag(repr(value))
        result.append(f"{color_repr(key, 'c')}: {text}")
    return "{" + ", ".join(result) + "}"
