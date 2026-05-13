from __future__ import annotations

import numpy as np


def analyze_illumination(image: np.ndarray | None) -> float:

    if image is None:
        return 0.0

    array = np.asarray(image, dtype=float)
    spread = float(array.std())
    return max(0.0, min(1.0, spread / 128.0))
