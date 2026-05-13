from __future__ import annotations

import cv2
import numpy as np


def analyze_blackscreen(image: np.ndarray | None) -> float:
    """Detect black screen photos.

    Black screens have very low brightness with many dark pixels.
    Also handles:
    - Overexposed black screens (e.g., black screen with white text/UI)
    - Flash overexposed black screens (camera flash on black screen)
    Returns a score in [0, 1] where higher means more likely a black screen.
    """

    if image is None:
        return 0.0

    array = np.asarray(image)
    if array.ndim == 3:
        gray = cv2.cvtColor(array, cv2.COLOR_BGR2GRAY).astype(float)
    else:
        gray = array.astype(float)

    mean_brightness = np.mean(gray)

    # Calculate ratio of very dark pixels (< 30 brightness)
    dark_ratio = float(np.sum(gray < 30) / gray.size)

    # Calculate ratio of very bright pixels (> 220 brightness)
    bright_ratio = float(np.sum(gray > 220) / gray.size)

    # Calculate ratio of dark pixels (< 50 brightness)
    dark_ratio_50 = float(np.sum(gray < 50) / gray.size)

    # Calculate standard deviation of brightness
    std_brightness = np.std(gray)

    # Case 1: Standard black screen - very low brightness
    if mean_brightness <= 70 and dark_ratio >= 0.3:
        dark_score = min(1.0, dark_ratio * 1.5)
        brightness_score = max(0.0, 1.0 - mean_brightness / 50.0)
        return max(0.0, min(1.0, float(dark_score * 0.6 + brightness_score * 0.4)))

    # Case 2: Overexposed black screen - high dark ratio with some bright areas
    # (e.g., black screen with white text/UI elements)
    if dark_ratio >= 0.4 and bright_ratio >= 0.2:
        dark_score = min(1.0, dark_ratio * 1.2)
        bimodal_score = min(1.0, (dark_ratio + bright_ratio) * 0.8)
        return max(0.0, min(1.0, dark_score * 0.5 + bimodal_score * 0.5))

    # Case 3: Very dark screen with some content
    if mean_brightness <= 50 and dark_ratio >= 0.5:
        return min(1.0, dark_ratio * 0.8)

    # Case 4: Flash overexposed black screen
    # High brightness from camera flash on black screen
    # Characteristics:
    # - High mean brightness (flash illuminated)
    # - Moderate dark regions (screen border, bezel, shadows)
    # - Low-to-moderate std (flash creates uniform lighting)
    # - NOT high-contrast content (which would have high std)
    # - Low bright_ratio (not many very bright pixels)
    if (
        mean_brightness > 100
        and std_brightness < 70
        and bright_ratio < 0.3
        and 0.03 <= dark_ratio_50 <= 0.3
    ):
        # Score based on how "flash overexposed" it looks
        # Higher brightness = more likely flash overexposure on dark surface
        brightness_factor = min(1.0, (mean_brightness - 80) / 80.0)
        # Some dark regions suggest it was originally dark
        dark_bonus = min(1.0, dark_ratio_50 * 5.0)
        # Combine: base score for high brightness + dark region bonus
        # Increased base score to better detect flash overexposed black screens
        score = 0.50 + brightness_factor * 0.25 + dark_bonus * 0.25
        return max(0.0, min(1.0, float(score)))

    return 0.0
