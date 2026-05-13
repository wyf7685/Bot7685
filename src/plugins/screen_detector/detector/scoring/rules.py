from __future__ import annotations

WEIGHTS = {
    "frequency": -0.15,
    "banding": 0.048,
    "blackscreen": 0.03,
    "chroma": -0.055,
    "softness": 0.181,
    "illumination": 0.131,
    "artifact": -0.081,
    "rectangle": 0.111,
    "display_content": -0.116,
    "overexposed": -0.002,
    "perspective": -0.013,
    "moire": -0.060,
    "reflection": -0.008,
    "sensor_noise": 0.15,
    "subpixel_fringing": -0.009,
    "exif_camera": 0.054,
    "format_score": 0.088,
    "color_noise": 0.020,
}

THRESHOLD = 0.23


def compute_score(features: dict[str, float]) -> float:
    return sum(
        float(features.get(name, 0.0)) * weight for name, weight in WEIGHTS.items()
    )


def classify_score(score: float, features: dict[str, float] | None = None) -> str:
    adjusted_score = score

    if features:
        sensor = float(features.get("sensor_noise", 0.0))
        softness = float(features.get("softness", 0.0))
        artifact = float(features.get("artifact", 0.0))
        moire = float(features.get("moire", 0.0))
        blackscreen = float(features.get("blackscreen", 0.0))

        # Rule 1: UI screenshot with abnormally high sensor noise
        # Dark-themed UI screenshots can trigger high sensor_noise due to fine
        # texture patterns. When combined with low softness, low artifact,
        # and high moire (pixel-level rendering patterns), this indicates a
        # normal screenshot, not a camera photo of a screen.
        if sensor > 0.95 and softness < 0.74 and artifact < 0.10 and moire > 0.80:
            adjusted_score -= 0.12

        # Rule 2: Black screen photo with high moire and softness
        # Camera photos of black screens show strong moire patterns from
        # sensor-pixel interference. High softness confirms camera capture.
        # Moderate blackscreen distinguishes from normal images with high moire.
        if moire > 0.95 and softness > 0.95 and blackscreen > 0.50:
            adjusted_score += 0.06

        # Rule 3: Normal screenshots with screen-photo-like features
        # Some screenshots have high softness, high moire, and low artifact
        # (clean capture without compression), which mimics screen photos.
        # High rectangle score (geometric structure) indicates a clean digital
        # screenshot rather than a camera-captured screen photo.
        rectangle = float(features.get("rectangle", 0.0))
        if softness > 0.90 and moire > 0.95 and artifact < 0.08 and rectangle > 0.10:
            adjusted_score -= 0.06

        # Rule 4: High softness + high moire + low artifact (moderate threshold)
        # Screenshots with moderately high softness (>0.80) and high moire
        # but low artifact are likely clean digital screenshots, not camera photos.
        if softness > 0.80 and moire > 0.90 and artifact < 0.10 and rectangle > 0.15:
            adjusted_score -= 0.08

    return "screen_photo" if adjusted_score >= THRESHOLD else "normal"
