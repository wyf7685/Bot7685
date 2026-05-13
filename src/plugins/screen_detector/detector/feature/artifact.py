from __future__ import annotations

import numpy as np


def analyze_artifact(image: np.ndarray | None) -> float:

    if image is None:
        return 0.0

    array = np.asarray(image, dtype=float)
    bright_ratio = float((array > 240).mean())
    return max(0.0, min(1.0, bright_ratio * 8.0))
