from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cv2.typing import MatLike


def analyze_banding(image: MatLike) -> float:
    try:
        import numpy as np
    except Exception:
        return 0.0

    if image is None:
        return 0.0

    array = np.asarray(image)
    if array.ndim == 3:
        array = array.mean(axis=2)

    row_diff = np.abs(np.diff(array, axis=0)).mean() if array.shape[0] > 1 else 0.0
    return max(0.0, min(1.0, float(row_diff) / 64.0))
