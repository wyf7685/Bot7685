from __future__ import annotations

import cv2
import numpy as np


def analyze_color_noise(image: np.ndarray | None) -> float:

    if image is None:
        return 0.0

    array = np.asarray(image)
    if array.ndim != 3:
        return 0.0

    hsv = cv2.cvtColor(array, cv2.COLOR_BGR2HSV)
    s = hsv[:, :, 1].astype(float)
    blurred_s = cv2.GaussianBlur(s, (5, 5), 0)
    residual = s - blurred_s
    return float(np.std(residual)) / 30.0
