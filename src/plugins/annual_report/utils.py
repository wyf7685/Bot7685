"""
QQ 群年度热词分析工具函数

本模块基于 https://github.com/ZiHuixi/QQgroup-annual-report-analyzer/commit/e0f0c474191c278da6be4857e99207a3127eec6e
在 MIT 协议下修改和使用

原项目版权：Copyright (c) 2025 ZiHuixi
"""

import math
import re
from collections import Counter
from datetime import datetime, timedelta, timezone


def extract_emojis(text: str) -> list[str]:
    emoji_pattern = re.compile(
        "["
        "\U0001f600-\U0001f64f"
        "\U0001f300-\U0001f5ff"
        "\U0001f680-\U0001f6ff"
        "\U0001f1e0-\U0001f1ff"
        "\U00002702-\U000027b0"
        "\U0001f900-\U0001f9ff"
        "\U0001fa00-\U0001fa6f"
        "\U0001fa70-\U0001faff"
        "\U00002600-\U000026ff"
        "\U00002300-\U000023ff"
        "]",
        flags=re.UNICODE,
    )
    return emoji_pattern.findall(text)


def is_emoji(char: str) -> bool:
    if len(char) != 1:
        return False
    code = ord(char)
    emoji_ranges = [
        (0x1F600, 0x1F64F),
        (0x1F300, 0x1F5FF),
        (0x1F680, 0x1F6FF),
        (0x1F1E0, 0x1F1FF),
        (0x2702, 0x27B0),
        (0x1F900, 0x1F9FF),
        (0x1FA00, 0x1FA6F),
        (0x1FA70, 0x1FAFF),
        (0x2600, 0x26FF),
        (0x2300, 0x23FF),
    ]
    return any(start <= code <= end for start, end in emoji_ranges)


def parse_timestamp(ts: str) -> int | None:
    """将时间戳解析为小时（CST 时区）

    Args:
        ts: ISO 8601 格式的时间戳字符串

    Returns:
        小时数 (0-23)，解析失败返回 None
    """
    try:
        return datetime.fromisoformat(ts).astimezone(timezone(timedelta(hours=8))).hour
    except Exception:
        return None


def clean_text(text: str) -> str:
    """清理文本，去除表情、@、回复等干扰内容

    Args:
        text: 原始文本

    Returns:
        清理后的文本
    """
    if not text:
        return ""

    # 1. 去除回复标记 [回复 xxx: yyy]
    text = re.sub(r"\[回复\s+[^\]]*\]", "", text)

    # 2. 去除@某人（包括群昵称中的空格、括号等）
    # 匹配 @ 开头，后面的所有内容直到遇到"空格+中文/字母"（实际消息内容的开始）
    text = re.sub(r"@[^\n]*?(?=\s+[\u4e00-\u9fffa-zA-Z])", "", text)
    # 处理只有@没有后续内容的情况
    text = re.sub(r"@[^\n]*$", "", text)

    # 3. 循环去除所有方括号内容（如[图片][表情]等）
    prev = None
    while prev != text:
        prev = text
        text = re.sub(r"\[[^\[\]]*\]", "", text)

    # 4. 去除链接
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"www\.\S+", "", text)

    # 5. 去除多余空白
    return re.sub(r"\s+", " ", text).strip()


def calculate_entropy(neighbor_freq: dict[str, int]) -> float:
    """计算邻接字符的熵值

    Args:
        neighbor_freq: 邻接字符的频率字典

    Returns:
        熵值（0 表示无变化）
    """
    total = sum(neighbor_freq.values())
    if total == 0:
        return 0.0
    entropy = 0.0
    for freq in neighbor_freq.values():
        p = freq / total
        if p > 0:
            entropy -= p * math.log2(p)
    return entropy


def generate_time_bar(hour_counts: dict[int, int], width: int = 20) -> list[str]:
    """生成 24 小时分布的条形图文本

    Args:
        hour_counts: 按小时统计的消息数量
        width: 条形图的宽度（字符数）

    Returns:
        每小时的条形图文本列表
    """
    max_count = max(hour_counts.values()) if hour_counts else 1
    lines = []
    for hour in range(24):
        count = hour_counts.get(hour, 0)
        bar_len = int(count / max_count * width) if max_count > 0 else 0
        bar = "█" * bar_len + "░" * (width - bar_len)
        percentage = (
            count * 100 / sum(hour_counts.values())
            if sum(hour_counts.values()) > 0
            else 0
        )
        lines.append(f"  {hour:02d}:00 {bar} {count:>5} ({percentage:>4.1f}%)")
    return lines


def analyze_single_chars(texts: list[str]) -> dict[str, tuple[int, float, float]]:
    """分析单字的独立出现情况

    Args:
        texts: 清理后的文本列表

    Returns:
        {字: (总次数, 独立次数, 独立比率)} 的字典
    """
    total_count: Counter[str] = Counter()
    solo_count: Counter[str] = Counter()
    boundary_count: Counter[str] = Counter()
    punctuation = set('，。！？、；：""（）,.!?;:\'"()[]【】《》<>…—～·')

    for text in texts:
        # 统计每个字的总出现次数
        for char in text:
            if re.match(r"^[\u4e00-\u9fffa-zA-Z]$", char):
                total_count[char] += 1

        # 统计单字消息
        clean_chars = [c for c in text if re.match(r"^[\u4e00-\u9fffa-zA-Z]$", c)]
        if len(clean_chars) == 1:
            solo_count[clean_chars[0]] += 1

        # 统计在边界位置的出现
        for i, char in enumerate(text):
            if not re.match(r"^[\u4e00-\u9fffa-zA-Z]$", char):
                continue
            left_ok = (
                (i == 0) or (text[i - 1] in punctuation) or (text[i - 1].isspace())
            )
            right_ok = (
                (i == len(text) - 1)
                or (text[i + 1] in punctuation)
                or (text[i + 1].isspace())
            )
            if left_ok and right_ok:
                boundary_count[char] += 1

    result: dict[str, tuple[int, float, float]] = {}
    for char in total_count:
        total = total_count[char]
        solo = solo_count[char]
        boundary = boundary_count[char]
        independent = solo + boundary * 0.5
        ratio = independent / total if total > 0 else 0.0
        result[char] = (total, independent, ratio)

    return result
