WEIGHTS = {
    "frequency": -0.251,
    "banding": 0.048,
    "chroma": -0.055,
    "softness": 0.181,
    "illumination": 0.131,
    "artifact": -0.081,
    "rectangle": 0.111,
    "display_content": -0.116,
    "overexposed": -0.002,
    "perspective": -0.013,
    "moire": -0.066,
    "reflection": -0.008,
    "sensor_noise": 0.215,
    "subpixel_fringing": -0.009,
    "exif_camera": 0.054,
    "format_score": 0.088,
    "color_noise": 0.020,
}

THRESHOLD = 0.248


def compute_score(features: dict[str, float]) -> float:
    return sum(
        float(features.get(name, 0.0)) * weight for name, weight in WEIGHTS.items()
    )


def classify_score(score: float) -> str:
    return "screen_photo" if score >= THRESHOLD else "normal"
