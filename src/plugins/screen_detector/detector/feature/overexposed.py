from __future__ import annotations

import numpy as np


def analyze_overexposed(image: np.ndarray | None) -> float:

    if image is None:
        return 0.0

    array = np.asarray(image, dtype=float)
    return max(0.0, min(1.0, float((array > 245).mean()) * 10.0))
