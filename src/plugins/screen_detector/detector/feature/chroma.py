from __future__ import annotations

import cv2
import numpy as np


def analyze_chroma(image: np.ndarray | None) -> float:

    if image is None:
        return 0.0

    if len(image.shape) == 2:
        return 0.0

    channels = cv2.split(image)
    spread = sum(float(np.std(channel)) for channel in channels) / len(channels)
    return max(0.0, min(1.0, spread / 128.0))
