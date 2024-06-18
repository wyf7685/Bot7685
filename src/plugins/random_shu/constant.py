import json
from pathlib import Path
from random import Random

random = Random()
router_path = "/random_shu/image"

# 图源: Bilibili@鱼烤箱
root = Path(__file__).parent.resolve()
image_dir = root / "images"
image_fps = list(image_dir.iterdir())
image_text: dict[str, str] = json.loads(
    (root / "text.json").read_text(encoding="utf-8")
)
