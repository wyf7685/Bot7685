from __future__ import annotations

import cv2
import numpy as np


def analyze_sensor_noise(image: np.ndarray | None) -> float:

    if image is None:
        return 0.0

    array = np.asarray(image)
    gray = cv2.cvtColor(array, cv2.COLOR_BGR2GRAY) if array.ndim == 3 else array

    gray = gray.astype(float)
    low_pass = cv2.GaussianBlur(gray, (9, 9), 0)
    residual = gray - low_pass
    edge_mask = cv2.Canny(gray.astype(np.uint8), 50, 150) == 0
    if not np.any(edge_mask):
        edge_mask = np.ones_like(gray, dtype=bool)

    noise = residual[edge_mask]
    if noise.size == 0:
        return 0.0

    score = float(np.std(noise)) / 18.0
    return max(0.0, min(1.0, score))
