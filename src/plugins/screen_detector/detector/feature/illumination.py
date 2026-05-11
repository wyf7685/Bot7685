from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cv2.typing import MatLike


def analyze_illumination(image: MatLike) -> float:
    try:
        import numpy as np
    except Exception:
        return 0.0

    if image is None:
        return 0.0

    array = np.asarray(image, dtype=float)
    spread = float(array.std())
    return max(0.0, min(1.0, spread / 128.0))
