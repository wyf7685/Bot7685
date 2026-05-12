"""人格档案清单加载与解析。"""

import json
from typing import Any

from nonebot import logger

from ..config import PROFILE_MANIFEST_FILE, config

DEFAULT_PROFILE_MAPPING = {
    "mbti": {
        "INTJ": {"code": "INTJ", "name_zh": "建筑师"},
        "INTP": {"code": "INTP", "name_zh": "逻辑学家"},
        "ENTJ": {"code": "ENTJ", "name_zh": "指挥官"},
        "ENTP": {"code": "ENTP", "name_zh": "辩论家"},
        "INFJ": {"code": "INFJ", "name_zh": "提倡者"},
        "INFP": {"code": "INFP", "name_zh": "调停者"},
        "ENFJ": {"code": "ENFJ", "name_zh": "主人公"},
        "ENFP": {"code": "ENFP", "name_zh": "竞选者"},
        "ISTJ": {"code": "ISTJ", "name_zh": "物流师"},
        "ISFJ": {"code": "ISFJ", "name_zh": "守卫者"},
        "ESTJ": {"code": "ESTJ", "name_zh": "总经理"},
        "ESTP": {"code": "ESTP", "name_zh": "企业家"},
        "ISTP": {"code": "ISTP", "name_zh": "鉴赏家"},
        "ISFP": {"code": "ISFP", "name_zh": "探险家"},
        "ESFJ": {"code": "ESFJ", "name_zh": "执政官"},
        "ESFP": {"code": "ESFP", "name_zh": "表演者"},
    },
    "sbti": {
        "INTJ": {"code": "CTRL", "name_zh": "拿捏者", "asset_code": "CTRL"},
        "INTP": {"code": "THIN-K", "name_zh": "思考者", "asset_code": "THIN-K"},
        "ENTJ": {"code": "BOSS", "name_zh": "领导者", "asset_code": "BOSS"},
        "ENTP": {"code": "JOKE-R", "name_zh": "小丑", "asset_code": "JOKE-R"},
        "INFJ": {"code": "LOVE-R", "name_zh": "多情者", "asset_code": "LOVE-R"},
        "INFP": {"code": "SOLO", "name_zh": "孤儿", "asset_code": "SOLO"},
        "ENFJ": {"code": "THAN-K", "name_zh": "感恩者", "asset_code": "THAN-K"},
        "ENFP": {"code": "GOGO", "name_zh": "行者", "asset_code": "GOGO"},
        "ISTJ": {"code": "OH-NO", "name_zh": "哦不人", "asset_code": "OH-NO"},
        "ISTP": {"code": "POOR", "name_zh": "贫困者", "asset_code": "POOR"},
        "ESTJ": {"code": "SHIT", "name_zh": "愤世者", "asset_code": "SHIT"},
        "ESTP": {"code": "WOC!", "name_zh": "握草人", "asset_code": "WOC"},
        "ISFJ": {"code": "MUM", "name_zh": "妈妈", "asset_code": "MUM"},
        "ISFP": {"code": "MALO", "name_zh": "吗喽", "asset_code": "MALO"},
        "ESFJ": {"code": "ATM-er", "name_zh": "送钱者", "asset_code": "ATM-er"},
        "ESFP": {"code": "SEXY", "name_zh": "尤物", "asset_code": "SEXY"},
    },
    "acgti": {
        "INTJ": {"code": "MRTS-X", "name_zh": "Mortis"},
        "INTP": {"code": "KNAN", "name_zh": "江户川柯南"},
        "ENTJ": {"code": "SAKI", "name_zh": "丰川祥子"},
        "ENTP": {"code": "CHKA", "name_zh": "藤原千花"},
        "INFJ": {"code": "DLRS", "name_zh": "三角初华"},
        "INFP": {"code": "BCHI", "name_zh": "后藤一里"},
        "ENFJ": {"code": "YCYO", "name_zh": "月见八千代"},
        "ENFP": {"code": "HTMK", "name_zh": "初音未来"},
        "ISTJ": {"code": "MRTS", "name_zh": "若叶睦"},
        "ISTP": {"code": "AYRE", "name_zh": "绫波丽"},
        "ESTJ": {"code": "MIKT", "name_zh": "御坂美琴"},
        "ESTP": {"code": "ASKA", "name_zh": "明日香"},
        "ISFJ": {"code": "SOYO", "name_zh": "长崎爽世"},
        "ISFP": {"code": "LTYI", "name_zh": "洛天依"},
        "ESFJ": {"code": "ANON", "name_zh": "千早爱音"},
        "ESFP": {"code": "FRNA", "name_zh": "芙宁娜"},
    },
}


class ProfileResolver:
    def __init__(self, profile_mode: str) -> None:
        self._manifest = self._load_manifest()
        self._profile_mode = profile_mode

    @staticmethod
    def _load_manifest() -> dict[str, dict[str, str]]:
        """加载人格资源清单。"""
        if not PROFILE_MANIFEST_FILE.exists():
            logger.warning(f"人格资源清单不存在: {PROFILE_MANIFEST_FILE}")
            return {"sbti": {}, "acgti": {}}

        try:
            raw: dict[str, list[dict[str, str]]] = json.loads(
                PROFILE_MANIFEST_FILE.read_text(encoding="utf-8-sig")
            )
        except Exception as e:
            logger.warning(f"加载人格资源清单失败: {e}")
            return {"sbti": {}, "acgti": {}}

        manifest: dict[str, dict] = {"sbti": {}, "acgti": {}}
        for item in raw.get("sbti", []):
            if code := str(item.get("code", "")).strip():
                manifest["sbti"][code] = item
        for item in raw.get("acgti", []):
            if code := str(item.get("code", "")).strip():
                manifest["acgti"][code] = item
        return manifest

    def _infer_image(self, asset_code: str) -> str:
        """当 manifest 缺少具体 code 时，根据已有资源路径模式推导图片地址。"""
        system_manifest = self._manifest.get(self._profile_mode, {})
        for item in system_manifest.values():
            if not isinstance(item, dict):
                continue
            sample_code = str(item.get("code", "")).strip()
            sample_file = str(item.get("file", "")).strip()
            if not sample_code or not sample_file:
                continue
            code_token = f"/{sample_code}."
            if code_token not in sample_file:
                continue
            return sample_file.replace(code_token, f"/{asset_code}.", 1)
        return ""

    def _get_profile_item(self, mbti: str) -> dict | None:
        """按 MBTI 从 manifest 中寻找可用资源。"""
        normalized_mbti = str(mbti or "").strip().upper()
        system_manifest = self._manifest.get(self._profile_mode, {})
        for item in system_manifest.values():
            if not isinstance(item, dict):
                continue
            item_mbti = str(item.get("mbti", "")).strip().upper()
            if item_mbti == normalized_mbti:
                return item
        return None

    def resolve(self, mbti: str) -> dict[str, Any]:
        """根据当前展示模式解析人格标签展示信息。"""
        profile_mode = self._profile_mode
        normalized_mbti = str(mbti or "").strip().upper()

        # 1. 基础信息获取：从默认映射中获取核心属性
        profile_defaults = DEFAULT_PROFILE_MAPPING.get(profile_mode, {})
        base_info = dict(profile_defaults.get(normalized_mbti, {}))

        code = str(base_info.get("code", normalized_mbti)).strip() or normalized_mbti
        name_zh = str(base_info.get("name_zh", "")).strip()
        asset_code = str(base_info.get("asset_code", code)).strip() or code
        image = str(base_info.get("image", "")).strip()

        # 2. 图片与属性补全 (基于 manifest.json 可信源)
        if not image:
            system_manifest = self._manifest.get(profile_mode, {})
            # A. 优先按 asset_code 索引
            asset_item = system_manifest.get(asset_code)
            if isinstance(asset_item, dict):
                image = str(asset_item.get("file", "")).strip()
                if not name_zh:
                    name_zh = str(asset_item.get("name", "")).strip()

            # B. 按照 asset_code 的资源规律推导图片地址
            #    (尝试根据同目录下其他资源的规律猜测当前角色的 CDN 地址)
            if not image:
                image = self._infer_image(asset_code)

            # C. 对于 acgti 模式，如果没找到明确映射也没能推导出图片，
            #    尝试通过 MBTI 反查该类型下的第一个可用资源作为兜底
            if not image and profile_mode == "acgti":
                fallback_item = self._get_profile_item(normalized_mbti)
                if isinstance(fallback_item, dict):
                    image = str(fallback_item.get("file", "")).strip()
                    if not name_zh:
                        name_zh = str(fallback_item.get("name", "")).strip()
                    if not code or code == normalized_mbti:
                        code = str(fallback_item.get("code", code)).strip()

        # 3. 构造显示文本 (Code + 中文名)
        display = str(base_info.get("display", "")).strip()
        if not display:
            display = f"{code}（{name_zh}）" if name_zh else code

        return {
            "profile_mode": profile_mode,
            "profile_code": code,
            "profile_name_zh": name_zh,
            "profile_display": display,
            "profile_image": image,
            "profile_image_opacity": config.render.profile_image_opacity,
            "profile_image_size_mode": config.render.profile_image_size_mode,
        }
