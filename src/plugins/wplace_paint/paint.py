from collections import defaultdict

import anyio

from .config import TemplateConfig, UserConfig
from .consts import COLORS_ID
from .fetch import fetch_me, post_paint_pixels
from .template import calc_template_diff


async def post_paint(
    user: UserConfig,
    tp: TemplateConfig,
    pawtect_token: str,
) -> int:
    count = (await fetch_me(user)).charges.count
    diff = await calc_template_diff(tp, include_pixels=True)
    pixels = [
        (tp.coords.offset(x, y), COLORS_ID[entry.name])
        for entry in diff
        for x, y in entry.pixels
    ][:count]

    if not pixels:
        return 0

    grouped = defaultdict[tuple[int, int], list[tuple[tuple[int, int], int]]](list)
    for coord, color_id in pixels:
        grouped[(coord.tlx, coord.tly)].append(((coord.pxx, coord.pxy), color_id))

    painted = 0

    for tile, tile_pixels in grouped.items():
        painted += await post_paint_pixels(user, pawtect_token, tile, tile_pixels)
        await anyio.sleep(3)

    return painted
