from __future__ import annotations

from pathlib import Path

from PIL import Image


def analyze_format_score(image_path: str | Path) -> float:
    try:
        with Image.open(str(image_path)) as img:
            fmt = img.format
        if fmt == "PNG":
            return 0.0
        if fmt in ("JPEG", "JPG"):
            return 0.5
        return 0.25  # noqa: TRY300
    except Exception:
        suffix = Path(image_path).suffix.lower()
        if suffix == ".png":
            return 0.0
        if suffix in (".jpg", ".jpeg"):
            return 0.5
        return 0.25
