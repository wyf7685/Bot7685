from __future__ import annotations

import cv2
import numpy as np


def analyze_frequency(image: np.ndarray | None) -> float:

    if image is None:
        return 0.0

    array = np.asarray(image)
    laplacian = cv2.Laplacian(array, cv2.CV_64F)
    variance = float(laplacian.var())
    return max(0.0, min(1.0, variance / 1000.0))
