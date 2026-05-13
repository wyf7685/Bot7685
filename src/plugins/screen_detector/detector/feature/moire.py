from __future__ import annotations

import cv2
import numpy as np


def analyze_moire(image: np.ndarray | None) -> float:

    if image is None:
        return 0.0

    array = np.asarray(image)
    gray = cv2.cvtColor(array, cv2.COLOR_BGR2GRAY) if array.ndim == 3 else array

    gray = gray.astype(float)
    height, width = gray.shape[:2]
    if height < 16 or width < 16:
        return 0.0

    block = 8
    h_blocks = height // block
    w_blocks = width // block
    if h_blocks < 2 or w_blocks < 2:
        return 0.0

    cropped = gray[: h_blocks * block, : w_blocks * block]
    reshaped = cropped.reshape(h_blocks, block, w_blocks, block)
    block_means = reshaped.mean(axis=(1, 3))
    block_vars = reshaped.var(axis=(1, 3))

    boundary_diffs_h = np.abs(np.diff(block_means, axis=0))
    boundary_diffs_v = np.abs(np.diff(block_means, axis=1))

    interior_vars = block_vars

    mean_boundary = float(
        np.mean(np.concatenate([boundary_diffs_h.ravel(), boundary_diffs_v.ravel()]))
    )
    mean_interior_std = float(np.mean(np.sqrt(interior_vars.ravel())))

    if mean_interior_std <= 0.0:
        return 0.0

    block_artifact_ratio = mean_boundary / (mean_interior_std + 1e-6)

    residual = gray.copy()
    blurred = cv2.GaussianBlur(gray, (3, 3), 0)
    residual = gray - blurred
    residual_blocks = residual[: h_blocks * block, : w_blocks * block].reshape(
        h_blocks, block, w_blocks, block
    )
    block_energy = np.var(residual_blocks, axis=(1, 3))
    energy_std = float(np.std(block_energy))
    energy_mean = float(np.mean(block_energy))

    freq_score = 0.0 if energy_mean <= 0.0 else energy_std / (energy_mean + 1e-6)

    score = (block_artifact_ratio * 0.4 + freq_score * 0.6) * 0.5
    return max(0.0, min(1.0, score))
