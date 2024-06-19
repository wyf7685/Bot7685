from pathlib import Path

router_path = "/random_shu/image"

# 图源: Bilibili@鱼烤箱
root = Path(__file__).parent.resolve()
image_dir = root / "images"
data_fp = root / "data.json"

emoji_weight_actions = {
    66: (+10, "增加"),  # 爱心
    76: (+5, "增加"),  # 大拇指(赞)
    265: (-5, "减少"),  # 老人手机
    38: (-10, "减少"),  # 敲打
}
