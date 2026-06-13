"""
QQ 群年度热词报告图片生成器

本模块基于 https://github.com/ZiHuixi/QQgroup-annual-report-analyzer/commit/e0f0c474191c278da6be4857e99207a3127eec6e
在 MIT 协议下修改和使用

原项目版权：Copyright (c) 2025 ZiHuixi
"""

import contextlib
import math
import random
from typing import Any

import httpx
from nonebot import logger
from nonebot_plugin_htmlrender import get_new_page, template_to_html

from .analyzer import ChatAnalyzer
from .config import TEMPLATE_FILE, config

# 每个词独立的贡献者颜色
WORD_COLORS = [
    "#DC2626",
    "#EA580C",
    "#D97706",
    "#CA8A04",
    "#65A30D",
    "#16A34A",
    "#0D9488",
    "#0891B2",
    "#2563EB",
    "#7C3AED",
]

# 榜单配置 (title, key, icon, unit)
RANKING_CONFIG = [
    ("群聊噪音", "话痨榜", "🏆", "条"),
    ("打字民工", "字数榜", "📝", "字"),
    ("小作文狂", "长文王", "📖", ""),
    ("表情狂人", "表情帝", "😂", "个"),
    ("我的图图", "图片狂魔", "🖼️", "张"),
    ("转发机器", "合并转发王", "📦", "次"),
    ("回复劳模", "回复狂", "💬", "次"),
    ("回复黑洞", "被回复最多", "⭐", "次"),
    ("艾特狂魔", "艾特狂", "📢", "次"),
    ("人气靶子", "被艾特最多", "🎯", "次"),
    ("链接仓鼠", "链接分享王", "🔗", "条"),
    ("阴间作息", "深夜党", "🌙", "条"),
    ("早八怨种", "早起鸟", "🌅", "条"),
    ("复读机器", "复读机", "🔄", "次"),
]


# filters
def format_number(value: int | str) -> str:
    """格式化数字"""
    try:
        return f"{int(value):,}"
    except Exception:
        return str(value)


def truncate_text(text: str | None, length: int = 50) -> str:
    """截断文本"""
    if not text:
        return ""
    text = text.replace("\n", " ").strip()
    if len(text) > length:
        return text[:length] + "..."
    return text


def get_avatar_url(uin: str | int) -> str:
    """获取 QQ 头像 URL"""
    return f"https://q1.qlogo.cn/g?b=qq&nk={uin}&s=640"


async def chat_completion(
    messages: list[dict[str, str]],
    max_tokens: int = 100,
    temperature: float = 0.7,
) -> str | None:
    """调用聊天完成 API

    Args:
        messages: 消息列表 [{"role": "user/system", "content": "..."}]
        max_tokens: 最大生成 token 数
        temperature: 温度参数

    Returns:
        API 返回的内容，或 None 表示失败
    """
    headers = {
        "Authorization": f"Bearer {config.openai.api_key}",
        "Content-Type": "application/json",
    }
    payload: dict[str, Any] = {
        "model": config.openai.model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }

    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                f"{config.openai.base_url}/chat/completions",
                json=payload,
                headers=headers,
            )

            if response.status_code != 200:
                logger.error(
                    f"❌ API 错误 ({response.status_code}): {response.text[:200]}"
                )
                return None

            data: dict[str, Any] = response.json()
            content: str | None = (
                data.get("choices", [{}])[0].get("message", {}).get("content")
            )

            if content is None:
                logger.error("❌ API 未返回任何内容")
                return None

            return content.strip()

    except httpx.TimeoutException:
        logger.error("❌ 请求超时，请检查网络或代理设置")
        return None
    except httpx.ConnectError:
        logger.error("❌ 连接失败，请检查代理配置")
        return None
    except Exception as e:
        logger.error(f"❌ 请求失败: {e}")
        return None


class AIWordSelector:
    """AI 智能选词器"""

    SYSTEM_PROMPT = """你是一个专业的群聊文化分析师，擅长识别最具代表性的群聊热词。

你的任务是从候选词列表中选出10个最适合作为年度热词的词汇。选词标准：
1. **使用量大**：高频出现的词更能代表群聊文化
2. **新颖有趣**：独特、有创意、有梗的词优先
3. **搞笑幽默**：能引发笑点的词、梗词、谐音梗等
4. **群聊特色**：体现这个群独特氛围和风格的词
5. **不避讳粗俗**：脏话、粗话、网络黑话如果有特色也可以选

优先考虑：
- 网络流行梗、热词
- 群内特有的黑话、缩写
- 搞笑表情、emoji组合
- 有趣的口头禅
- 独特的表达方式

请从提供的候选词中选出最能代表这个群聊文化的10个词。"""

    USER_PROMPT = """请从以下{}个候选词中选出10个最适合作为年度热词的词汇：

{}

要求：
1. 选出的词要有代表性、有趣味、有群聊特色
2. 优先选择使用量大且有特色的词
3. 不要回避脏话粗话，只要有特色就可以
4. 直接输出10个序号，用逗号分隔，例如: 1,5,8,12,15,23,30,42,56,78
5. 只输出序号，不要有其他文字
6. 尽量选择前100的，除非后面有特别有趣的词
7. 尽量不要选择"啊"等无意义填充词，除非在例句中使用的特别有趣"""

    async def select_words(
        self, candidate_words: list[dict[str, Any]], top_n: int = 200
    ) -> list[dict[str, Any]] | None:
        """从候选词中智能选出 10 个年度热词

        Args:
            candidate_words: 候选词列表
            top_n: 参与选择的前 N 个词

        Returns:
            选出的 10 个词，或 None 表示失败
        """
        # 准备候选词列表（取前 top_n 个）
        candidates: list[dict[str, Any]] = candidate_words[:top_n]

        # 构建候选词信息
        words_info: list[str] = []
        for idx, word_data in enumerate(candidates, 1):
            word: str = word_data["word"]
            freq: int = word_data["freq"]
            samples: list[str] = word_data.get("samples", [])
            sample_preview: str = samples[0][:30] if samples else "无样本"

            words_info.append(f"{idx}. {word} ({freq}次) - 样本: {sample_preview}")

        words_text: str = "\n".join(words_info)
        user_prompt: str = self.USER_PROMPT.format(len(candidates), words_text)

        try:
            result: str | None = await chat_completion(
                messages=[
                    {"role": "system", "content": self.SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                max_tokens=100,
                temperature=0.7,
            )

            if result is None:
                return None

            # 解析序号
            indices: list[int] = []
            for part in result.replace("，", ",").split(","):
                with contextlib.suppress(Exception):
                    idx = int(part.strip())
                    if 1 <= idx <= len(candidates):
                        indices.append(idx - 1)  # 转为 0 索引

            if len(indices) < 10:
                logger.warning(f"⚠️  AI 只选出 {len(indices)} 个词，自动补充前几个...")
                # 补充前面的词直到 10 个
                for i in range(len(candidates)):
                    if i not in indices and len(indices) < 10:
                        indices.append(i)

            indices = indices[:10]
            selected: list[dict[str, Any]] = [candidates[i] for i in indices]

            logger.success("\n✅ AI 选词完成:")
            for i, word_data in enumerate(selected, 1):
                logger.success(f"   {i}. {word_data["word"]} ({word_data["freq"]}次)")

        except Exception:
            logger.exception("❌ AI 选词失败")
            return None

        else:
            return selected


def _fallback_comment() -> str:
    """备用锐评"""
    fallbacks: list[str] = [
        "群友的快乐，简单又纯粹",
        "这个词承载了太多故事",
        "高频出现，必有原因",
        "群聊精华，浓缩于此",
        "每一次使用都是一次认同",
    ]
    return random.choice(fallbacks)


class AICommentGenerator:
    """AI 锐评生成器"""

    SYSTEM_PROMPT = """\
你是一个幽默风趣的群聊分析师，擅长用犀利又不失温度的语言点评网络热词。

你的任务是为 QQ 群年度热词报告生成一句精辟的锐评。要求：
1. 简短有力，15-30 字为宜
2. 可以调侃、可以感慨、可以哲理，但要有趣
3. 结合词语本身的含义和使用场景
4. 语气可以是：毒舌吐槽/温情感慨/哲学思考/冷幽默/谐音梗 等
5. 不要太正经，要有网感

风格参考：
- "哈哈哈" → "快乐是假的，但敷衍是真的"
- "牛逼" → "词汇量告急时的唯一出路"
- "好的" → "成年人最敷衍的三个字"
- "?" → "一个符号，十万种质疑"
- "6" → "当代网友最高效的赞美"""

    USER_PROMPT = """请为这个群聊热词生成一句锐评：

词语：{}
出现次数：{}次
使用样本：
{}

直接输出锐评内容，不要加引号或其他格式。"""

    async def generate_comment(
        self, word: str, freq: int, samples: list[str] | None = None
    ) -> str:
        """为单个词生成锐评

        Args:
            word: 词语
            freq: 出现次数
            samples: 使用样本

        Returns:
            锐评内容
        """
        # 构建用户提示
        samples_text: str = (
            "\n".join(f"- {s[:50]}" for s in samples[:5]) if samples else "无"
        )

        user_prompt = self.USER_PROMPT.format(word, freq, samples_text)
        messages = [
            {"role": "system", "content": self.SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]

        try:
            result = await chat_completion(messages, 100, 0.9)
            return result or _fallback_comment()
        except Exception:
            logger.exception(f"   ⚠️  AI 生成失败({word})")
            return _fallback_comment()

    async def generate_batch(self, words_data: list[dict[str, Any]]) -> dict[str, str]:
        """批量生成锐评

        Args:
            words_data: 词汇数据列表

        Returns:
            {词: 锐评} 的字典
        """
        comments: dict[str, str] = {}
        for word_info in words_data:
            comment = await self.generate_comment(
                word=word_info["word"],
                freq=word_info["freq"],
                samples=word_info.get("samples", []),
            )
            comments[word_info["word"]] = comment
        return comments


class ImageGenerator:
    """图片报告生成器"""

    def __init__(self, analyzer: ChatAnalyzer) -> None:
        self.analyzer: ChatAnalyzer | None = analyzer
        self.json_data: dict[str, Any] | None = None
        self.selected_words: list[dict[str, Any]] = []
        self.ai_comments: dict[str, str] = {}
        self.json_data = analyzer.export_json()
        self.ai_selector: AIWordSelector | None = None

    def _prepare_template_data(self) -> dict[str, Any]:
        """准备模板数据"""
        if not self.json_data:
            return {}

        max_freq: int = max(w["freq"] for w in self.selected_words)
        min_freq: int = min(w["freq"] for w in self.selected_words)

        def calc_bar_height(freq: int) -> float:
            if max_freq == min_freq:
                return 80
            normalized: float = (freq - min_freq) / (max_freq - min_freq)
            return 25 + math.sqrt(normalized) * 75

        processed_words: list[dict[str, Any]] = []
        for idx, word_info in enumerate(self.selected_words):
            contributors: list[dict[str, Any]] = word_info.get("contributors", [])
            total: int = word_info["freq"]

            # 每个词独立分配颜色给其贡献者
            segments: list[dict[str, Any]] = []
            accounted: int = 0
            word_contributor_colors: dict[str, str] = {}

            for i, c in enumerate(contributors[:5]):
                color: str = WORD_COLORS[i % len(WORD_COLORS)]
                word_contributor_colors[c["name"]] = color
                percent: float = (c["count"] / total * 100) if total > 0 else 0
                segments.append(
                    {
                        "name": c["name"],
                        "uin": c.get("uin", ""),
                        "count": c["count"],
                        "percent": percent,
                        "color": color,
                    }
                )
                accounted += c["count"]

            # 其他
            if accounted < total:
                other: int = total - accounted
                segments.append(
                    {
                        "name": "其他",
                        "uin": "",
                        "count": other,
                        "percent": (other / total * 100),
                        "color": "#6B7280",
                    }
                )

            # 图例（该词的贡献者）
            legend: list[dict[str, Any]] = [
                {
                    "name": c["name"],
                    "color": word_contributor_colors.get(c["name"], "#6B7280"),
                }
                for c in contributors[:3]
            ]
            while len(legend) < 3:
                legend.append({"name": "", "color": "transparent"})

            # 主要贡献者文本
            contrib_text: str = (
                "、".join(c["name"] for c in contributors[:3])
                if contributors
                else "未知"
            )

            # AI 锐评
            ai_comment: str = self.ai_comments.get(word_info["word"], "")

            processed_words.append(
                {
                    "word": word_info["word"],
                    "freq": word_info["freq"],
                    "bar_height": calc_bar_height(word_info["freq"]),
                    "segments": segments,
                    "legend": legend,
                    "samples": word_info.get("samples", []),
                    "contributors_text": contrib_text,
                    "top_contributor": contributors[0] if contributors else None,
                    "ai_comment": ai_comment,
                    "color": WORD_COLORS[idx % len(WORD_COLORS)],
                }
            )

        # 榜单数据
        rankings_data: dict[str, Any] = self.json_data.get("rankings", {})
        processed_rankings: list[dict[str, Any]] = []

        for title, key, icon, unit in RANKING_CONFIG:
            data: list[dict[str, Any]] = rankings_data.get(key, [])
            if not data:
                continue

            first: dict[str, Any] | None = data[0] if data else None
            others: list[dict[str, Any]] = data[1:5] if len(data) > 1 else []

            processed_rankings.append(
                {
                    "title": title,
                    "icon": icon,
                    "unit": unit,
                    "first": {
                        "name": first.get("name", "未知"),
                        "uin": first.get("uin", ""),
                        "value": first.get("value", 0),
                        "avatar": (
                            get_avatar_url(first.get("uin", "")) if first else ""
                        ),
                    }
                    if first
                    else None,
                    "others": [
                        {
                            "name": item.get("name", "未知"),
                            "value": item.get("value", 0),
                            "uin": item.get("uin", ""),
                            "avatar": get_avatar_url(item.get("uin", "")),
                        }
                        for item in others
                    ],
                }
            )

        # 24 小时分布
        hour_dist: dict[str, int] = self.json_data.get("hourDistribution", {})
        max_hour: int = max(
            (int(hour_dist.get(str(h), 0)) for h in range(24)), default=1
        )
        peak_hour: int = max(range(24), key=lambda h: int(hour_dist.get(str(h), 0)))

        hour_data: list[dict[str, int | float]] = []
        for h in range(24):
            count: int = int(hour_dist.get(str(h), 0))
            height: float = max((count / max_hour * 100) if max_hour > 0 else 0, 3)
            hour_data.append({"hour": h, "count": count, "height": height})

        return {
            "chat_name": self.json_data.get("chatName", "未知群聊"),
            "message_count": self.json_data.get("messageCount", 0),
            "selected_words": processed_words,
            "rankings": processed_rankings,
            "hour_data": hour_data,
            "peak_hour": peak_hour,
        }

    async def _generate_ai_comments(self) -> None:
        """生成 AI 锐评（可静默）"""
        self.ai_comments = await AICommentGenerator().generate_batch(
            self.selected_words
        )

    async def _render_report(self) -> bytes | None:
        html = await template_to_html(
            template_path=str(TEMPLATE_FILE.parent),
            template_name=TEMPLATE_FILE.name,
            filters={
                "format_number": format_number,
                "truncate_text": truncate_text,
                "avatar_url": get_avatar_url,
            },
            **self._prepare_template_data(),
        )

        async with get_new_page(
            viewport={"width": 450, "height": 800},
            device_scale_factor=3,
        ) as page:
            await page.set_content(html)
            await page.wait_for_timeout(2000)
            height: int = await page.evaluate("document.body.scrollHeight")
            await page.set_viewport_size({"width": 450, "height": height + 50})
            await page.wait_for_timeout(500)
            return await page.screenshot(full_page=True)

    async def generate(self) -> bytes | None:
        """生成报告

        Args:
            auto_select: 自动选择前 10 个（简单模式）
            ai_select: 使用 AI 智能选词（从前 200 个中选出最有趣的 10 个）
            non_interactive: 非交互模式
            generate_image: 是否生成图片
            enable_ai: 是否启用 AI 锐评

        Returns:
            (HTML 路径, 图片路径) 的元组
        """
        if not self.json_data:
            logger.warning("❌ 无数据")
            return None

        top_words: list[dict[str, Any]] = self.json_data.get("topWords", [])
        if not top_words:
            logger.warning("❌ 无热词数据")
            return None

        # 初始化 AI 选词器
        if not self.ai_selector:
            self.ai_selector = AIWordSelector()

        # AI 选词
        self.selected_words = (
            await self.ai_selector.select_words(top_words, top_n=200) or top_words[:10]
        )

        if not self.selected_words:
            logger.warning("⚠️  AI 选词失败，改用自动选择前 10 个")
            self.selected_words = top_words[:10]

        if not self.selected_words:
            return None

        # AI 锐评
        await self._generate_ai_comments()
        return await self._render_report()
