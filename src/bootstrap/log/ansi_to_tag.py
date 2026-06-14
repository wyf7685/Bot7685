import re
from typing import Final

from .config import escape_tag


class Style:
    RESET_ALL = 0
    BOLD = 1
    DIM = 2
    ITALIC = 3
    UNDERLINE = 4
    BLINK = 5
    REVERSE = 7
    HIDE = 8
    STRIKE = 9
    NORMAL = 22


class Fore:
    BLACK = 30
    RED = 31
    GREEN = 32
    YELLOW = 33
    BLUE = 34
    MAGENTA = 35
    CYAN = 36
    WHITE = 37
    RESET = 39

    LIGHTBLACK_EX = 90
    LIGHTRED_EX = 91
    LIGHTGREEN_EX = 92
    LIGHTYELLOW_EX = 93
    LIGHTBLUE_EX = 94
    LIGHTMAGENTA_EX = 95
    LIGHTCYAN_EX = 96
    LIGHTWHITE_EX = 97


class Back:
    BLACK = 40
    RED = 41
    GREEN = 42
    YELLOW = 43
    BLUE = 44
    MAGENTA = 45
    CYAN = 46
    WHITE = 47
    RESET = 49

    LIGHTBLACK_EX = 100
    LIGHTRED_EX = 101
    LIGHTGREEN_EX = 102
    LIGHTYELLOW_EX = 103
    LIGHTBLUE_EX = 104
    LIGHTMAGENTA_EX = 105
    LIGHTCYAN_EX = 106
    LIGHTWHITE_EX = 107


# Splits a log line into alternating plain-text and ESC[…m tokens.
_SGR_RE: Final = re.compile(r"(\x1b\[[0-9;]*m)")

# Terminal 16-colour palette (indices 0-7 normal, 8-15 bright).
_PALETTE: Final[tuple[tuple[int, int, int], ...]] = (
    (0x0C, 0x0C, 0x0C),  # 0  black
    (0xC5, 0x0F, 0x1F),  # 1  red
    (0x13, 0xA1, 0x0E),  # 2  green
    (0xC1, 0x9C, 0x00),  # 3  yellow
    (0x00, 0x37, 0xDA),  # 4  blue
    (0x88, 0x17, 0x98),  # 5  magenta
    (0x3A, 0x96, 0xDD),  # 6  cyan
    (0xCC, 0xCC, 0xCC),  # 7  white
    (0x76, 0x76, 0x76),  # 8  bright black (dark grey)
    (0xE7, 0x48, 0x56),  # 9  bright red
    (0x16, 0xC6, 0x0C),  # 10 bright green
    (0xF9, 0xF1, 0xA5),  # 11 bright yellow
    (0x3B, 0x78, 0xFF),  # 12 bright blue
    (0xB4, 0x00, 0x9E),  # 13 bright magenta
    (0x61, 0xD6, 0xD6),  # 14 bright cyan
    (0xF2, 0xF2, 0xF2),  # 15 bright white
)


def _cube_component(c: int) -> int:
    return 0 if c == 0 else 55 + c * 40


def _palette_256(n: int) -> tuple[int, int, int]:
    if n < 16:
        return _PALETTE[n]
    if n < 232:
        n -= 16
        r, g, b = n // 36, (n // 6) % 6, n % 6
        return (_cube_component(r), _cube_component(g), _cube_component(b))
    v = 8 + (n - 232) * 10
    return (v, v, v)


# ---------------------------------------------------------------------------
# ANSI SGR code → loguru tag name
# ---------------------------------------------------------------------------

_STYLE_MAP: Final[dict[int, str]] = {
    Style.BOLD: "bold",
    Style.DIM: "dim",
    Style.ITALIC: "italic",
    Style.UNDERLINE: "underline",
    Style.BLINK: "blink",
    Style.REVERSE: "reverse",
    Style.HIDE: "hide",
    Style.STRIKE: "strike",
    Style.NORMAL: "normal",
}

_FG_MAP: Final[dict[int, str]] = {
    Fore.BLACK: "black",
    Fore.RED: "red",
    Fore.GREEN: "green",
    Fore.YELLOW: "yellow",
    Fore.BLUE: "blue",
    Fore.MAGENTA: "magenta",
    Fore.CYAN: "cyan",
    Fore.WHITE: "white",
    Fore.LIGHTBLACK_EX: "light-black",
    Fore.LIGHTRED_EX: "light-red",
    Fore.LIGHTGREEN_EX: "light-green",
    Fore.LIGHTYELLOW_EX: "light-yellow",
    Fore.LIGHTBLUE_EX: "light-blue",
    Fore.LIGHTMAGENTA_EX: "light-magenta",
    Fore.LIGHTCYAN_EX: "light-cyan",
    Fore.LIGHTWHITE_EX: "light-white",
}

_BG_MAP: Final[dict[int, str]] = {
    Back.BLACK: "BLACK",
    Back.RED: "RED",
    Back.GREEN: "GREEN",
    Back.YELLOW: "YELLOW",
    Back.BLUE: "BLUE",
    Back.MAGENTA: "MAGENTA",
    Back.CYAN: "CYAN",
    Back.WHITE: "WHITE",
    Back.LIGHTBLACK_EX: "LIGHT-BLACK",
    Back.LIGHTRED_EX: "LIGHT-RED",
    Back.LIGHTGREEN_EX: "LIGHT-GREEN",
    Back.LIGHTYELLOW_EX: "LIGHT-YELLOW",
    Back.LIGHTBLUE_EX: "LIGHT-BLUE",
    Back.LIGHTMAGENTA_EX: "LIGHT-MAGENTA",
    Back.LIGHTCYAN_EX: "LIGHT-CYAN",
    Back.LIGHTWHITE_EX: "LIGHT-WHITE",
}


def _codes_to_tags(codes: list[int]) -> list[str]:
    """将 ANSI SGR 参数序列转换为 loguru 标签名列表。"""
    tags: list[str] = []
    i = 0
    while i < len(codes):
        c = codes[i]
        if c == 38 and i + 2 < len(codes) and codes[i + 1] == 5:
            tags.append(f"fg {codes[i + 2]}")
            i += 3
        elif c == 48 and i + 2 < len(codes) and codes[i + 1] == 5:
            tags.append(f"bg {codes[i + 2]}")
            i += 3
        elif c == 38 and i + 4 < len(codes) and codes[i + 1] == 2:
            r, g, b = codes[i + 2], codes[i + 3], codes[i + 4]
            tags.append(f"fg #{r:02x}{g:02x}{b:02x}")
            i += 5
        elif c == 48 and i + 4 < len(codes) and codes[i + 1] == 2:
            r, g, b = codes[i + 2], codes[i + 3], codes[i + 4]
            tags.append(f"bg #{r:02x}{g:02x}{b:02x}")
            i += 5
        elif c in _FG_MAP:
            tags.append(_FG_MAP[c])
            i += 1
        elif c in _BG_MAP:
            tags.append(_BG_MAP[c])
            i += 1
        elif c in _STYLE_MAP:
            tags.append(_STYLE_MAP[c])
            i += 1
        else:
            i += 1
    return tags


def ansi_to_tag(color_message: str) -> str:
    """将 uvicorn ``color_message`` 中的 ANSI 转义序列转换为 loguru 标签格式。"""
    parts: list[str] = []
    tags: list[str] = []  # 已打开的标签栈
    last_end = 0

    for match in _SGR_RE.finditer(color_message):
        start = match.start()
        if start > last_end:
            parts.append(escape_tag(color_message[last_end:start]))

        # match.group(1) 形如 "\x1b[36m" 或 "\x1b[38;5;150m"
        raw = match.group(1)
        codes_str = raw[2:-1]  # 去掉前导 "\x1b[" 和尾部 "m"
        codes = [int(c) for c in codes_str.split(";") if c] if codes_str else [0]

        if codes == [0]:
            parts.extend("</>" * len(tags))
            tags.clear()
        else:
            new_tags = _codes_to_tags(codes)
            parts.extend(f"<{tag}>" for tag in new_tags)
            tags.extend(new_tags)

        last_end = match.end()

    if last_end < len(color_message):
        parts.append(escape_tag(color_message[last_end:]))

    return "".join(parts)
