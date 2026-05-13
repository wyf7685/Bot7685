from __future__ import annotations

import cv2
import numpy as np


def analyze_display_content(image: np.ndarray | None) -> float:

    if image is None:
        return 0.0

    array = np.asarray(image)
    gray = cv2.cvtColor(array, cv2.COLOR_BGR2GRAY) if array.ndim == 3 else array

    edges = cv2.Canny(gray, 60, 140)
    edge_density = float(np.count_nonzero(edges)) / float(edges.size or 1)

    vertical_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, 9))
    horizontal_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (9, 1))
    vertical_lines = cv2.morphologyEx(edges, cv2.MORPH_OPEN, vertical_kernel)
    horizontal_lines = cv2.morphologyEx(edges, cv2.MORPH_OPEN, horizontal_kernel)
    line_density = float(
        np.count_nonzero(vertical_lines) + np.count_nonzero(horizontal_lines)
    ) / float(edges.size or 1)

    std_score = float(np.std(gray)) / 128.0
    score = edge_density * 3.0 + line_density * 2.0 + std_score * 0.5
    return max(0.0, min(1.0, score))
