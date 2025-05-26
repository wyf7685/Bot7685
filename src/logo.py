from collections.abc import Callable
from typing import Literal

COLORIZER: dict[Literal["rich", "ansi"], Callable[[int, int, int, str], str]] = {
    "rich": (lambda r, g, b, c: f"<fg #{r:02x}{g:02x}{b:02x}>{c}</>"),
    "ansi": (lambda r, g, b, c: f"\033[38;2;{r};{g};{b}m{c}\033[0m"),
}


def apply_gradient_2d(
    lines: list[str],
    start: tuple[int, int, int],
    end: tuple[int, int, int],
    mode: Literal["rich", "ansi"],
) -> list[str]:
    if not lines:
        return []

    h = len(lines)
    w = max(map(len, lines))
    denominator = (w - 1) ** 2 + (h - 1) ** 2
    r1, g1, b1 = start
    r2, g2, b2 = end
    colored_lines: list[str] = []
    colorizer = COLORIZER[mode]

    for row, line in enumerate(lines):
        colored_line: list[str] = []
        for col, char in enumerate(line):
            t = max(0, min(1, (col * (w - 1) + row * (h - 1)) / denominator))
            r = int(r1 + (r2 - r1) * t)
            g = int(g1 + (g2 - g1) * t)
            b = int(b1 + (b2 - b1) * t)
            colored_line.append(colorizer(r, g, b, char))

        colored_lines.append("".join(colored_line))

    return colored_lines


# https://www.lddgo.net/string/text-to-ascii-art
LOGO_LINES = """\
██████╗  ██████╗ ████████╗███████╗ ██████╗  █████╗ ███████╗
██╔══██╗██╔═══██╗╚══██╔══╝╚════██║██╔════╝ ██╔══██╗██╔════╝
██████╔╝██║   ██║   ██║       ██╔╝███████╗ ╚█████╔╝███████╗
██╔══██╗██║   ██║   ██║      ██╔╝ ██╔═══██╗██╔══██╗╚════██║
██████╔╝╚██████╔╝   ██║      ██║  ╚██████╔╝╚█████╔╝███████║
╚═════╝  ╚═════╝    ╚═╝      ╚═╝   ╚═════╝  ╚════╝ ╚══════╝
""".strip().splitlines()
WIDTH = max(map(len, LOGO_LINES))

st1 = (255, 132, 90)
ed1 = (139, 211, 71)
st2 = (141, 209, 71)
ed2 = (71, 203, 209)


def render() -> list[str]:
    split = int(WIDTH * 0.7)
    part1 = apply_gradient_2d([line[:split] for line in LOGO_LINES], st1, ed1, "rich")
    part2 = apply_gradient_2d([line[split:] for line in LOGO_LINES], st2, ed2, "rich")
    return [a + b for a, b in zip(part1, part2, strict=True)]


def print_logo(log: Callable[[str], object]) -> None:
    split = "━" * WIDTH
    log(split)
    for line in render():
        log(line)
    log(split)
