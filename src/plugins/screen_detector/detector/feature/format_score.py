import contextlib
from pathlib import Path


def analyze_format_score(image_path: str | Path) -> float:
    fmt = Path(image_path).suffix.lower().removeprefix(".").upper()
    with contextlib.suppress(Exception):
        from PIL import Image

        with Image.open(image_path) as img:
            fmt = img.format

    if fmt == "PNG":
        return 0.0
    if fmt in ("JPEG", "JPG"):
        return 0.5
    return 0.25
