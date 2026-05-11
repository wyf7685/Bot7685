from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cv2.typing import MatLike


def preprocess_image(image: MatLike) -> MatLike:
    try:
        import cv2
    except Exception:
        return image

    if image is None:
        return image

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    return cv2.GaussianBlur(gray, (3, 3), 0)
