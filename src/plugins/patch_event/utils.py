from typing import Any

from nonebot.utils import escape_tag


def color_repr(value: Any, /, *color: str) -> str:
    text = escape_tag(repr(value))
    for c in reversed(color):
        text = f"<{c}>{text}</{c}>"
    return text


def highlight_object(value: Any, /, *color: str) -> str:
    if isinstance(value, dict):
        return highlight_dict(value, *color)
    if isinstance(value, list):
        return highlight_list(value, *color)
    if isinstance(value, set):
        return highlight_set(value, *color)
    if isinstance(value, tuple):
        return highlight_tuple(value, *color)
    return color_repr(value, *color)


def highlight_dict(data: dict[str, Any], /, *color: str) -> str:
    return (
        "{"
        + ", ".join(
            f"{color_repr(key, 'c')}: {highlight_object(value, *color)}"
            for key, value in data.items()
        )
        + "}"
    )


def highlight_list(data: list[Any], /, *color: str) -> str:
    return "[" + ", ".join(highlight_object(item, *color) for item in data) + "]"


def highlight_set(data: set[Any], /, *color: str) -> str:
    return "{" + ", ".join(highlight_object(item, *color) for item in data) + "}"


def highlight_tuple(data: tuple[Any], /, *color: str) -> str:
    return "(" + ", ".join(highlight_object(item, *color) for item in data) + ")"
