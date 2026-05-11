from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cv2.typing import MatLike


def analyze_softness(image: MatLike) -> float:
    try:
        import cv2
        import numpy as np
    except Exception:
        return 0.0

    if image is None:
        return 0.0

    array = np.asarray(image)
    if array.ndim == 3:
        array = cv2.cvtColor(array, cv2.COLOR_BGR2GRAY)

    blur = cv2.GaussianBlur(array, (5, 5), 0)
    variance = float(cv2.Laplacian(blur, cv2.CV_64F).var())
    softness = 1.0 - min(1.0, variance / 500.0)
    return max(0.0, softness)
