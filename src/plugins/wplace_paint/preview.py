import io

import anyio
import anyio.to_thread
import httpx
from PIL import Image

from .config import proxy
from .utils import (
    WplacePixelCoords,
    fix_coords,
    get_all_tile_coords,
    get_size,
    parse_rgb_str,
)

TILE_URL = "https://backend.wplace.live/files/s0/tiles/{x}/{y}.png"


async def download_preview(
    coord1: WplacePixelCoords,
    coord2: WplacePixelCoords,
    background: str | None = None,
) -> bytes:
    coord1, coord2 = fix_coords(coord1, coord2)
    tile_imgs: dict[tuple[int, int], bytes] = {}

    async def fetch_tile(x: int, y: int) -> None:
        resp = await client.get(TILE_URL.format(x=x, y=y))
        tile_imgs[(x, y)] = resp.raise_for_status().read()

    async with (
        httpx.AsyncClient(proxy=proxy) as client,
        anyio.create_task_group() as tg,
    ):
        for x, y in get_all_tile_coords(coord1, coord2):
            tg.start_soon(fetch_tile, x, y)

    def create_image() -> bytes:
        bg_color = (0, 0, 0, 0)
        if background is not None and (bg_rgb := parse_rgb_str(background)):
            bg_color = (*bg_rgb, 255)

        img = Image.new("RGBA", get_size(coord1, coord2), bg_color)
        for (tx, ty), tile_bytes in tile_imgs.items():
            tile_img = Image.open(io.BytesIO(tile_bytes)).convert("RGBA")
            src_box = (
                0 if tx != coord1.tlx else coord1.pxx,
                0 if ty != coord1.tly else coord1.pxy,
                1000 if tx != coord2.tlx else coord2.pxx + 1,
                1000 if ty != coord2.tly else coord2.pxy + 1,
            )
            paste_pos = (
                (tx - coord1.tlx) * 1000 - (0 if tx == coord1.tlx else coord1.pxx),
                (ty - coord1.tly) * 1000 - (0 if ty == coord1.tly else coord1.pxy),
            )
            src = tile_img.crop(src_box)
            img.paste(src, paste_pos, src.getchannel("A"))

        with io.BytesIO() as output:
            img.save(output, format="PNG")
            return output.getvalue()

    return await anyio.to_thread.run_sync(create_image)
