from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cv2.typing import MatLike


def analyze_frequency(image: MatLike) -> float:
    try:
        import cv2
        import numpy as np
    except Exception:
        return 0.0

    if image is None:
        return 0.0

    array = np.asarray(image)
    laplacian = cv2.Laplacian(array, cv2.CV_64F)
    variance = float(laplacian.var())
    return max(0.0, min(1.0, variance / 1000.0))
