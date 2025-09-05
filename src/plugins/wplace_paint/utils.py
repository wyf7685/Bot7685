import re
from dataclasses import dataclass


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


BLUE_MARBLE_COORDS_PATTERN = re.compile(
    r".+?Tl X: (\d+), Tl Y: (\d+), Px X: (\d+), Px Y: (\d+).+?"
)


def parse_coords(s: str) -> WplacePixelCoords:
    if not (m := BLUE_MARBLE_COORDS_PATTERN.match(s)):
        raise ValueError(f"Invalid coords: {s}")
    return WplacePixelCoords(int(m[1]), int(m[2]), int(m[3]), int(m[4]))
