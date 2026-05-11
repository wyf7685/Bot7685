from __future__ import annotations

from pathlib import Path


def camera_exif_score(image_path: str | Path) -> float:
    try:
        from PIL import ExifTags, Image
    except Exception:
        return 0.0

    try:
        with Image.open(Path(image_path)) as image:
            exif = image.getexif()
    except Exception:
        return 0.0

    if not exif:
        return 0.0

    tags = {ExifTags.TAGS.get(key, key): value for key, value in exif.items()}
    software = str(tags.get("Software", "")).lower()
    make = str(tags.get("Make", "")).strip()
    model = str(tags.get("Model", "")).strip()

    if any(
        keyword in software
        for keyword in ("screenshot", "screen capture", "screen shot")
    ):
        return 0.0

    if make or model:
        return 0.6

    if software:
        return 0.15

    return 0.0
