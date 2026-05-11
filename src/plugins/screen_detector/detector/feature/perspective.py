from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cv2.typing import MatLike


def analyze_perspective(image: MatLike) -> float:
    try:
        import cv2
        import numpy as np
    except Exception:
        return 0.0

    if image is None:
        return 0.0

    array = np.asarray(image)
    gray = cv2.cvtColor(array, cv2.COLOR_BGR2GRAY) if array.ndim == 3 else array

    gray_f = gray.astype(float)
    laplacian = np.abs(cv2.Laplacian(gray_f, cv2.CV_64F))
    sobelx = np.abs(cv2.Sobel(gray_f, cv2.CV_64F, 1, 0, ksize=3))
    sobely = np.abs(cv2.Sobel(gray_f, cv2.CV_64F, 0, 1, ksize=3))
    gradient_mag = np.sqrt(sobelx**2 + sobely**2)

    threshold = np.percentile(gradient_mag, 90)
    edge_mask = gradient_mag > threshold
    if not np.any(edge_mask):
        return 0.0

    lap_at_edges = float(np.mean(laplacian[edge_mask]))
    grad_at_edges = float(np.mean(gradient_mag[edge_mask]))

    if grad_at_edges <= 0.0:
        return 0.0

    sharpness_ratio = lap_at_edges / grad_at_edges
    score = min(1.0, sharpness_ratio / 0.4)
    return max(0.0, score)
