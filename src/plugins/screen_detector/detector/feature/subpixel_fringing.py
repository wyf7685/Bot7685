from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cv2.typing import MatLike


def analyze_subpixel_fringing(image: MatLike) -> float:
    try:
        import cv2
        import numpy as np
    except Exception:
        return 0.0

    if image is None:
        return 0.0

    array = np.asarray(image)
    if array.ndim != 3 or array.shape[2] < 3:
        return 0.0

    gray = cv2.cvtColor(array, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 50, 150)
    edge_mask = edges > 0
    if not np.any(edge_mask):
        return 0.0

    blue, green, red = cv2.split(array.astype(float))
    channel_spread = np.abs(red - green) + np.abs(green - blue) + np.abs(red - blue)
    spread_score = float(channel_spread[edge_mask].mean()) / 255.0
    return max(0.0, min(1.0, spread_score))
