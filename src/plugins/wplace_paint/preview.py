import io
import re
from dataclasses import dataclass

import anyio
import anyio.to_thread
import httpx
from PIL import Image

from .config import proxy

TILE_URL = "https://backend.wplace.live/files/s0/tiles/{x}/{y}.png"


@dataclass
class WplacePixelCoords:
    # each tile contains 1000x1000 pixels, from 0 to 999
    tlx: int  # tile X
    tly: int  # tile Y
    pxx: int  # pixel X
    pxy: int  # pixel Y


def fix_coords(
    coord1: WplacePixelCoords,
    coord2: WplacePixelCoords,
) -> tuple[WplacePixelCoords, WplacePixelCoords]:
    x1, x2 = sorted((coord1.tlx * 1000 + coord1.pxx, coord2.tlx * 1000 + coord2.pxx))
    y1, y2 = sorted((coord1.tly * 1000 + coord1.pxy, coord2.tly * 1000 + coord2.pxy))
    return (
        WplacePixelCoords(x1 // 1000, y1 // 1000, x1 % 1000, y1 % 1000),
        WplacePixelCoords(x2 // 1000, y2 // 1000, x2 % 1000, y2 % 1000),
    )


def get_all_tile_coords(
    coord1: WplacePixelCoords,
    coord2: WplacePixelCoords,
) -> list[tuple[int, int]]:
    coord1, coord2 = fix_coords(coord1, coord2)
    return [
        (x, y)
        for x in range(coord1.tlx, coord2.tlx + 1)
        for y in range(coord1.tly, coord2.tly + 1)
    ]


def get_size(
    coord1: WplacePixelCoords,
    coord2: WplacePixelCoords,
) -> tuple[int, int]:
    coord1, coord2 = fix_coords(coord1, coord2)
    width = (coord2.tlx - coord1.tlx) * 1000 + (coord2.pxx - coord1.pxx) + 1
    height = (coord2.tly - coord1.tly) * 1000 + (coord2.pxy - coord1.pxy) + 1
    return width, height


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
        if (
            background is not None
            and (bg := background.removeprefix("#").lower())
            and len(bg) == 6
            and all(c in "0123456789abcdef" for c in bg)
        ):
            bg_color = (*(int(bg[i : i + 2], 16) for i in (0, 2, 4)), 255)

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


BLUE_MARBLE_COORDS_PATTERN = re.compile(
    r".+?Tl X: (\d+), Tl Y: (\d+), Px X: (\d+), Px Y: (\d+).+?"
)


def parse_coords(s: str) -> WplacePixelCoords:
    if not (m := BLUE_MARBLE_COORDS_PATTERN.match(s)):
        raise ValueError(f"Invalid coords: {s}")
    return WplacePixelCoords(int(m[1]), int(m[2]), int(m[3]), int(m[4]))
