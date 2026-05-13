from __future__ import annotations

import cv2
import numpy as np


def preprocess_image(image: np.ndarray | None) -> np.ndarray | None:

    if image is None:
        return image

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    return cv2.GaussianBlur(gray, (3, 3), 0)
