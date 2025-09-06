# ruff: noqa: E501
import base64
import colorsys
import functools
import io
from typing import TYPE_CHECKING

from PIL import Image, ImageDraw


def _generate_avatar(s: str) -> bytes:
    # fmt: off
    h = (int(functools.reduce(lambda h, ch: (int(h) & 0xFFFFFFFF ^ ord(ch)) * -5., s, 5.)) & 0xFFFFFFFF) >> 2
    f = tuple(int(c * 255) for c in colorsys.hls_to_rgb(((h % 9) * (360 / 9)) / 360.0, 0.45, 0.95))
    d = ImageDraw.Draw(i := Image.new("RGB", (300, 300), color="#F0F0F0"))
    for c in filter(lambda c: h & (1 << (c % 15)), range(25)):
        x, y = 25 + 50 * (col if (col := c // 5) < 3 else 5 - (col - 2)), 25 + 50 * (c % 5)
        d.rectangle((x, y, x + 50, y + 50), f)
    with io.BytesIO() as b:
        return i.save(b, format="PNG") or b.getvalue()


def get_wplace_avatar(s: str) -> str:
    data = _generate_avatar(s)
    return f"data:image/png;base64,{base64.b64encode(data).decode()}"


if not TYPE_CHECKING:
    get_wplace_avatar = functools.lru_cache(maxsize=16)(get_wplace_avatar)
