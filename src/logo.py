from collections.abc import Callable


def apply_gradient_2d(
    lines: list[str],
    start: tuple[int, int, int],
    end: tuple[int, int, int],
) -> list[str]:
    h = len(lines)
    w = max(map(len, lines)) if lines else 0
    r1, g1, b1 = start
    r2, g2, b2 = end
    colored_lines = []
    denominator = (w - 1) ** 2 + (h - 1) ** 2

    for row, line in enumerate(lines):
        colored_line = []
        for col, char in enumerate(line):
            # 计算梯度因子 t
            if denominator == 0:  # 文本只有一个字符 (W=1, H=1)
                t = 0
            elif h == 1:  # 只有一行 (纯水平渐变)
                t = col / (w - 1) if w > 1 else 0  # 如果只有1列，因子为0
            elif w == 1:  # 只有一列 (纯垂直渐变)
                t = row / (h - 1) if h > 1 else 0  # 如果只有1行，因子为0
            else:  # 正常二维渐变
                t = (col * (w - 1) + row * (h - 1)) / denominator

            # 插值
            t = max(0, min(1, t))
            r = int(r1 + (r2 - r1) * t)
            g = int(g1 + (g2 - g1) * t)
            b = int(b1 + (b2 - b1) * t)

            # 应用颜色
            colored_line.append(f"<fg #{r:02x}{g:02x}{b:02x}>{char}</>")

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
    part1 = apply_gradient_2d([line[:split] for line in LOGO_LINES], st1, ed1)
    part2 = apply_gradient_2d([line[split:] for line in LOGO_LINES], st2, ed2)
    return [a + b for a, b in zip(part1, part2, strict=True)]


def print_logo(log: Callable[[str], object]) -> None:
    split = "━" * WIDTH
    log(split)
    for line in render():
        log(line)
    log(split)
