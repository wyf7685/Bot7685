from __future__ import annotations

import cv2
import numpy as np


def analyze_reflection(image: np.ndarray | None) -> float:

    if image is None:
        return 0.0

    array = np.asarray(image)
    if array.ndim == 3:
        gray = cv2.cvtColor(array, cv2.COLOR_BGR2GRAY)
        hsv = cv2.cvtColor(array, cv2.COLOR_BGR2HSV)
        value_channel = hsv[:, :, 2].astype(float)
    else:
        gray = array.astype(float)
        value_channel = gray

    local_mean = cv2.blur(gray, (9, 9))
    local_variance = cv2.blur((gray - local_mean) ** 2, (9, 9))
    local_std = np.sqrt(local_variance)

    bright_threshold = float(np.percentile(value_channel, 97))
    bright_mask = value_channel >= bright_threshold
    if not np.any(bright_mask):
        return 0.0

    texture_threshold = float(np.percentile(local_std, 40))
    low_texture_mask = local_std <= texture_threshold
    reflection_mask = bright_mask & low_texture_mask

    bright_ratio = float(np.count_nonzero(bright_mask)) / float(bright_mask.size or 1)
    reflection_ratio = float(np.count_nonzero(reflection_mask)) / float(
        reflection_mask.size or 1
    )
    score = (bright_ratio * 4.0) + (reflection_ratio * 8.0)
    return max(0.0, min(1.0, score))
