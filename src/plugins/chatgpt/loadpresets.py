import json
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional

import chardet
from nonebot.log import logger
from pydantic import BaseModel, ValidationError, field_validator

from .config import plugin_config

# 在这里统一写进字典后不需要改动其他地方的代码了
# 字典的key会保存为Preset的name以及文件名
PRESET_PROMPTS: Dict[str, List[Dict[str, str]]] = {
    "ChatGPT": [
        {
            "role": "user",
            "content": (
                "You are ChatGPT, a large language model trained by OpenAI. Respond conversationally. Do not answer as the user.\n"
                f"Current date: {date.today()}"
            ),
        },
        {
            "role": "assistant",
            "content": "Hello! How can I help you today?",
        },
    ],
}


class Preset(BaseModel):
    """
    预设模板类
    """

    name: str
    preset: List[Dict[str, str]]
    preset_id: int

    @field_validator("preset")
    def preset_validator(cls, v):
        if all(v):
            return v
        raise ValueError("preset 为空")

    def __str__(self) -> str:
        return f"{self.preset_id}:{self.name}"

    @staticmethod
    def presets2str(presets: List["Preset"]) -> str:
        """
        根据输入的预设模板列表生成回复字符串
        """
        answer: str = "请选择模板:"
        for preset in presets:
            answer += f"\n{preset}"
        return answer


def CreateBasicPresetJson(path: Path) -> None:
    """
    根据 PRESET_PROMPTS 创建基本预设模板的 json文件
    """
    for name, prompt in PRESET_PROMPTS.items():
        create_preset2json(prompt, path / f"{name}.json")


def create_preset2json(
    prompt: list,
    filepath: Path,
    encoding: str = "utf8",
    ensure_ascii: bool = False,
    **kwargs,
) -> None:
    """
    根据输入的 prompt 和文件路径创建模板 json文件
    如果文件路径已存在则直接返回
    """
    if filepath.exists():
        return
    dir_path: Path = filepath.parent
    file_name: str = filepath.name
    preset_name: str = filepath.stem
    if not dir_path.is_dir():
        logger.info(
            f"{filepath}文件夹下{preset_name}基础预设不存在,将自动创建{file_name}"
        )
        dir_path.mkdir(parents=True)
    try:
        with open(filepath, "w", encoding=encoding) as f:
            json.dump(prompt, f, ensure_ascii=ensure_ascii, **kwargs)
    except Exception:
        logger.error(f"创建{file_name}失败!")
    else:
        logger.success(f"创建{file_name}成功!")


def load_preset(filepath: Path, num: int, encoding: str = "utf8") -> Optional[Preset]:
    """
    加载路径下的模板 json文件
    """

    try:
        preset_data: List[dict] = json.loads(filepath.read_text(encoding=encoding))
    except json.JSONDecodeError:
        logger.error(f"预设: {filepath.stem} 读取失败! encoding {encoding}")
        return

    try:
        preset = Preset(
            name=filepath.stem,
            preset=preset_data,
            preset_id=num,
        )
    except ValidationError:
        logger.error(f"预设: {filepath.stem} 解析失败! encoding {encoding}")
        return

    logger.success(f"预设: {filepath.stem} 读取成功!")
    return preset


def get_encoding(file_path: Path) -> str:
    """
    检测文件编码，需要 chardet 依赖
    """
    return chardet.detect(file_path.read_bytes()).get("encoding") or "utf-8"


def load_all_preset(path: Path) -> List[Preset]:
    """
    加载指定文件夹下所有模板 json文件，返回 Preset列表
    """
    if not path.exists():
        path.mkdir(parents=True)
    presets: List[Preset] = []
    CreateBasicPresetJson(path)
    for file in path.rglob("*.json"):
        preset = load_preset(file, len(presets) + 1)
        if preset is None:
            preset = load_preset(file, len(presets) + 1, encoding=get_encoding(file))
        if preset is not None:
            presets.append(preset)
    if len(presets) > 0:
        logger.success(f"此次共成功加载{len(presets)}个预设")
    else:
        logger.error("未成功加载任何预设!")
    return presets


preset_path: Path = plugin_config.preset_path
presets_list: List[Preset] = load_all_preset(preset_path)
presets_str: str = Preset.presets2str(presets_list)
templateDict: Dict[str, Preset] = {
    str(preset.preset_id): preset for preset in presets_list
}
