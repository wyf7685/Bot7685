"""
QQ 群年度热词分析器

本模块基于 https://github.com/ZiHuixi/QQgroup-annual-report-analyzer/commit/e0f0c474191c278da6be4857e99207a3127eec6e
在 MIT 协议下修改和使用

原项目版权：Copyright (c) 2025 ZiHuixi
"""

import math
import random
import re
import string
from collections import Counter, defaultdict
from typing import Any

import jieba
from nonebot import logger

from .config import config
from .schema import AnalyzerInput, Message
from .utils import (
    analyze_single_chars,
    calculate_entropy,
    clean_text,
    extract_emojis,
    is_emoji,
    parse_timestamp,
)

PUNCTUATION = string.punctuation + "，。！？；：、''（）【】"


class ChatAnalyzer:
    """QQ 群聊分析器"""

    def __init__(self, data: AnalyzerInput) -> None:
        """初始化分析器

        Args:
            data: 符合 AnalyzerInput 模型的输入数据
        """
        self.data = data
        self.messages = data.messages
        self.chat_name: str = (
            data.chatName
            or (data.chatInfo.name if data.chatInfo else None)
            or "未知群聊"
        )

        # 映射和统计
        self.uin_to_name: dict[str | int, str] = {}
        self.msgid_to_sender: dict[str, str | int] = {}

        # 词频统计
        self.word_freq: Counter[str] = Counter()
        self.word_samples: defaultdict[str, list[str]] = defaultdict(list)
        self.word_contributors: defaultdict[str, Counter[str | int]] = defaultdict(
            Counter
        )

        # 用户统计
        self.user_msg_count: Counter[str | int] = Counter()
        self.user_char_count: Counter[str | int] = Counter()
        self.user_char_per_msg: dict[str | int, float] = {}
        self.user_image_count: Counter[str | int] = Counter()
        self.user_forward_count: Counter[str | int] = Counter()
        self.user_reply_count: Counter[str | int] = Counter()
        self.user_replied_count: Counter[str | int] = Counter()
        self.user_at_count: Counter[str | int] = Counter()
        self.user_ated_count: Counter[str | int] = Counter()
        self.user_emoji_count: Counter[str | int] = Counter()
        self.user_link_count: Counter[str | int] = Counter()
        self.user_night_count: Counter[str | int] = Counter()
        self.user_morning_count: Counter[str | int] = Counter()
        self.user_repeat_count: Counter[str | int] = Counter()

        # 时间分布
        self.hour_distribution: Counter[int] = Counter()

        # 新词发现和合并
        self.discovered_words: set[str] = set()
        self.merged_words: dict[str, tuple[str, str, int, float]] = {}

        # 单字统计
        self.single_char_stats: dict[str, tuple[int, float, float]] = {}
        self.cleaned_texts: list[str] = []

        self._build_mappings()

    def _is_bot_message(self, msg: Message) -> bool:
        """判断是否为机器人消息（基于 subMsgType）

        Args:
            msg: 消息对象

        Returns:
            是否为机器人消息
        """
        if not config.filter.filter_bot_messages:
            return False

        sub_msg_type: int = msg.rawMessage.subMsgType
        return sub_msg_type in [577, 65]

    def _build_mappings(self) -> None:
        """构建 UIN 到昵称的映射，优先保留有效的 name"""
        uin_names: defaultdict[str | int, list[str]] = defaultdict(list)
        uin_member_names: dict[str | int, str] = {}

        for msg in self.messages:
            if self._is_bot_message(msg):
                continue

            uin: str | int = msg.sender.uin
            name: str = msg.sender.name.strip()
            msg_id: str = msg.messageId

            # 收集 name
            if uin and name and (not uin_names[uin] or uin_names[uin][-1] != name):
                uin_names[uin].append(name)

            # 收集 sendMemberName（保留最后一个）
            send_member_name: str | None = msg.rawMessage.sendMemberName
            if uin and send_member_name:
                uin_member_names[uin] = send_member_name.strip()

            # 构建消息 ID 到发送者的映射
            if msg_id and uin:
                self.msgid_to_sender[msg_id] = uin

        # 为每个 UIN 选择最合适的 name
        for uin, names in uin_names.items():
            chosen_name: str | None = None

            # 从后往前找第一个不等于 uin 的 name
            for name in reversed(names):
                if name != str(uin):
                    chosen_name = name
                    break

            # 如果所有 name 都等于 uin，使用 sendMemberName
            if chosen_name is None:
                if uin in uin_member_names:
                    chosen_name = uin_member_names[uin]
                elif names:
                    chosen_name = names[-1]

            if chosen_name:
                self.uin_to_name[uin] = chosen_name

    def get_name(self, uin: str | int) -> str:
        """获取用户昵称

        Args:
            uin: 用户 UIN

        Returns:
            用户昵称
        """
        return self.uin_to_name.get(uin, f"未知用户({uin})")

    def analyze(self) -> None:
        """执行完整分析流程"""
        logger.info(f"📊 开始分析: {self.chat_name}")
        logger.info(f"📝 消息数: {len(self.messages)}")

        logger.info("\n🧹 预处理文本...")
        self._preprocess_texts()

        logger.info("🔤 分析单字独立性...")
        self.single_char_stats = analyze_single_chars(self.cleaned_texts)

        logger.info("🔍 新词发现...")
        self._discover_new_words()

        logger.info("🔗 词组合并...")
        self._merge_word_pairs()

        logger.info("📈 分词统计...")
        self._tokenize_and_count()

        logger.info("🎮 趣味统计...")
        self._fun_statistics()

        logger.info("🧹 过滤整理...")
        self._filter_results()

        logger.info("✅ 完成!")

    def _preprocess_texts(self) -> None:
        """预处理所有文本"""
        skipped: int = 0
        bot_filtered: int = 0

        for msg in self.messages:
            if self._is_bot_message(msg):
                bot_filtered += 1
                continue

            text: str = msg.content.text
            cleaned: str = clean_text(text)

            if cleaned and len(cleaned) >= 1:
                self.cleaned_texts.append(cleaned)
            elif text:
                skipped += 1

        if config.filter.filter_bot_messages and bot_filtered > 0:
            logger.info(
                f"   有效文本: {len(self.cleaned_texts)} 条, "
                f"跳过: {skipped} 条, 过滤机器人: {bot_filtered} 条"
            )
        else:
            logger.info(
                f"   有效文本: {len(self.cleaned_texts)} 条, 跳过: {skipped} 条"
            )

    def _discover_new_words(self) -> None:
        """新词发现"""
        ngram_freq: Counter[str] = Counter()
        left_neighbors: defaultdict[str, Counter[str]] = defaultdict(Counter)
        right_neighbors: defaultdict[str, Counter[str]] = defaultdict(Counter)
        total_chars: int = 0

        for text in self.cleaned_texts:
            sentences: list[str] = re.split(
                '[，。！？、；：""（）\\s\\n\\r,.!?()\\[\\]]', text
            )

            for sentence in sentences:
                sentence = sentence.strip()
                if len(sentence) < 2:
                    continue

                total_chars += len(sentence)

                for n in range(2, min(6, len(sentence) + 1)):
                    for i in range(len(sentence) - n + 1):
                        ngram: str = sentence[i : i + n]

                        # 跳过纯数字/符号/纯英文
                        if re.match(r"^[\d\s\W]+$", ngram) or re.match(
                            r"^[a-zA-Z]+$", ngram
                        ):
                            continue

                        ngram_freq[ngram] += 1

                        if i > 0:
                            left_neighbors[ngram][sentence[i - 1]] += 1
                        else:
                            left_neighbors[ngram]["<BOS>"] += 1

                        if i + n < len(sentence):
                            right_neighbors[ngram][sentence[i + n]] += 1
                        else:
                            right_neighbors[ngram]["<EOS>"] += 1

        # 筛选新词
        for word, freq in ngram_freq.items():
            if freq < config.new_word_discovery.new_word_min_freq:
                continue

            # 邻接熵
            left_ent: float = calculate_entropy(left_neighbors[word])
            right_ent: float = calculate_entropy(right_neighbors[word])
            min_ent: float = min(left_ent, right_ent)

            if min_ent < config.new_word_discovery.entropy_threshold:
                continue

            # PMI（内部凝聚度）
            min_pmi: float = float("inf")
            for i in range(1, len(word)):
                left_freq: int = ngram_freq.get(word[:i], 0)
                right_freq: int = ngram_freq.get(word[i:], 0)

                if left_freq > 0 and right_freq > 0:
                    pmi: float = math.log2(
                        (freq * total_chars) / (left_freq * right_freq + 1e-10)
                    )
                    min_pmi = min(min_pmi, pmi)

            if min_pmi == float("inf"):
                min_pmi = 0

            if min_pmi < config.new_word_discovery.pmi_threshold:
                continue

            self.discovered_words.add(word)

        # 添加到 jieba 词典
        for word in self.discovered_words:
            jieba.add_word(word, freq=1000)

        logger.info(f"   发现 {len(self.discovered_words)} 个新词")

    def _merge_word_pairs(self) -> None:
        """词组合并"""
        bigram_counter: Counter[tuple[str, str]] = Counter()
        word_right_counter: Counter[str] = Counter()

        for text in self.cleaned_texts:
            words: list[str] = [w for w in jieba.cut(text) if w.strip()]

            for i in range(len(words) - 1):
                w1: str = words[i].strip()
                w2: str = words[i + 1].strip()

                if not w1 or not w2:
                    continue

                if re.match(r"^[\d\W]+$", w1) or re.match(r"^[\d\W]+$", w2):
                    continue

                bigram_counter[(w1, w2)] += 1
                word_right_counter[w1] += 1

        # 找出应该合并的词对
        for (w1, w2), count in bigram_counter.items():
            merged: str = w1 + w2

            if len(merged) > config.word_merge.merge_max_len:
                continue
            if count < config.word_merge.merge_min_freq:
                continue

            # 条件概率 P(w2|w1)
            if word_right_counter[w1] > 0:
                prob: float = count / word_right_counter[w1]
                if prob >= config.word_merge.merge_min_prob:
                    self.merged_words[merged] = (w1, w2, count, prob)
                    jieba.add_word(merged, freq=count * 1000)

        logger.info(f"   合并 {len(self.merged_words)} 个词组")

        # 显示前几个
        if self.merged_words:
            sorted_merges: list[tuple[str, tuple[str, str, int, float]]] = sorted(
                self.merged_words.items(), key=lambda x: -x[1][2]
            )[:10]
            for merged, (w1, w2, cnt, prob) in sorted_merges:
                logger.info(f"      {merged}: {w1}+{w2} ({cnt}次, {prob:.0%})")

    def _tokenize_and_count(self) -> None:
        """分词统计"""
        for msg in self.messages:
            if self._is_bot_message(msg):
                continue

            sender_uin: str | int = msg.sender.uin
            text: str = msg.content.text
            cleaned: str = clean_text(text)

            if not cleaned:
                continue

            words: list[str] = list(jieba.cut(cleaned))
            emojis: list[str] = extract_emojis(cleaned)
            words = [w for w in words if not is_emoji(w)]
            all_tokens: list[str] = words + emojis

            for word in all_tokens:
                word = word.strip()
                if not word:
                    continue

                # 跳过纯数字/符号
                if re.match(r"^[\d\W]+$", word) and not is_emoji(word):
                    continue

                self.word_freq[word] += 1
                self.word_contributors[word][sender_uin] += 1

                if len(self.word_samples[word]) < config.analysis.sample_count * 3:
                    self.word_samples[word].append(cleaned)

    def _fun_statistics(self) -> None:
        """趣味统计"""
        prev_clean: str | None = None
        prev_sender: str | int | None = None

        for msg in self.messages:
            if self._is_bot_message(msg):
                continue

            sender_uin: str | int = msg.sender.uin
            text: str = msg.content.text
            timestamp: str = msg.timestamp

            self.user_msg_count[sender_uin] += 1
            clean: str = clean_text(text)
            self.user_char_count[sender_uin] += len(clean)

            # 图片检测（排除 GIF）
            if "[图片:" in text and ".gif" not in text.lower():
                self.user_image_count[sender_uin] += 1

            # 转发检测
            if "[合并转发:" in text:
                self.user_forward_count[sender_uin] += 1

            # 回复统计
            if msg.content.reply:
                self.user_reply_count[sender_uin] += 1
                ref_msg_id: str = msg.content.reply.referencedMessageId
                if ref_msg_id in self.msgid_to_sender:
                    target_uin: str | int = self.msgid_to_sender[ref_msg_id]
                    self.user_replied_count[target_uin] += 1

            # @ 统计
            for elem in msg.rawMessage.elements:
                if elem.elementType == 1 and elem.textElement:
                    at_type: int = elem.textElement.atType
                    at_uid: str = elem.textElement.atUid
                    if at_type > 0 and at_uid and at_uid != "0":
                        self.user_at_count[sender_uin] += 1
                        self.user_ated_count[at_uid] += 1

            # 表情统计（包括 emoji、[表情:]、GIF）
            emojis: list[str] = extract_emojis(clean)
            gif_count: int = text.lower().count(".gif")
            bracket_emoji_count: int = text.count("[表情:")
            emoji_count: int = len(emojis) + bracket_emoji_count + gif_count

            if emoji_count > 0:
                self.user_emoji_count[sender_uin] += emoji_count

            # 链接统计
            if "[链接:" in text or re.search(r"https?://", text):
                self.user_link_count[sender_uin] += 1

            # 时段统计
            hour: int | None = parse_timestamp(timestamp)
            if hour is not None:
                self.hour_distribution[hour] += 1
                if hour in config.time.night_owl_hours:
                    self.user_night_count[sender_uin] += 1
                if hour in config.time.early_bird_hours:
                    self.user_morning_count[sender_uin] += 1

            # 复读统计（用清理后文本，且内容要有意义）
            if (
                clean
                and len(clean) >= 2
                and clean == prev_clean
                and sender_uin != prev_sender
            ):
                self.user_repeat_count[sender_uin] += 1

            prev_clean = clean if clean else prev_clean
            prev_sender = sender_uin

        # 计算人均字数
        for uin in self.user_msg_count:
            msg_count: int = self.user_msg_count[uin]
            char_count: int = self.user_char_count[uin]
            if msg_count >= 10:
                self.user_char_per_msg[uin] = char_count / msg_count

    def _filter_results(self) -> None:
        """过滤结果"""
        filtered_freq: Counter[str] = Counter()

        for word, freq in self.word_freq.items():
            # 长度过滤
            if (
                len(word) < config.analysis.min_word_len
                or len(word) > config.analysis.max_word_len
            ):
                continue
            if freq < config.analysis.min_freq:
                continue

            # 白名单直接通过
            if word in config.filter.whitelist:
                filtered_freq[word] = freq
                continue

            # 黑名单跳过
            if word in config.filter.blacklist:
                continue

            # 停用词（emoji 除外）
            if word in config.filter.stopwords and not is_emoji(word):
                continue

            # 单字特殊处理
            if len(word) == 1:
                if is_emoji(word):
                    pass  # emoji 保留
                else:
                    stats = self.single_char_stats.get(word)
                    if stats:
                        _, indep, ratio = stats
                        if (
                            ratio < config.single_char.single_min_solo_ratio
                            or indep < config.single_char.single_min_solo_count
                        ):
                            continue
                    else:
                        continue

            # 纯数字跳过
            if re.match(r"^[\d\s]+$", word):
                continue

            # 纯标点跳过
            if all(c in PUNCTUATION for c in word):
                continue

            filtered_freq[word] = freq

        self.word_freq = filtered_freq

        # 采样
        for word in self.word_samples:
            samples: list[str] = self.word_samples[word]
            if len(samples) > config.analysis.sample_count:
                self.word_samples[word] = random.sample(
                    samples, config.analysis.sample_count
                )

        logger.info(f"   过滤后 {len(self.word_freq)} 个词")

    def get_top_words(self, n: int | None = None) -> list[tuple[str, int]]:
        """获取高频词

        Args:
            n: 返回的词数，默认使用配置值

        Returns:
            (词, 频率) 的列表
        """
        n = n or config.analysis.top_n
        return self.word_freq.most_common(n)

    def get_word_detail(self, word: str) -> dict[str, Any]:
        """获取词的详细信息

        Args:
            word: 词语

        Returns:
            包含词频、样例、贡献者的字典
        """
        return {
            "word": word,
            "freq": self.word_freq.get(word, 0),
            "samples": self.word_samples.get(word, []),
            "contributors": [
                (self.get_name(uin), count)
                for uin, count in self.word_contributors[word].most_common(
                    config.analysis.contributor_top_n
                )
            ],
        }

    def get_fun_rankings(self) -> dict[str, list[tuple[str, Any]]]:
        """获取趣味排行榜

        Returns:
            各种排行榜的字典
        """
        rankings: dict[str, list[tuple[str, Any]]] = {}

        def fmt(
            counter: Counter[str | int], top_n: int = config.analysis.contributor_top_n
        ) -> list[tuple[str, Any]]:
            return [
                (self.get_name(uin), count) for uin, count in counter.most_common(top_n)
            ]

        rankings["话痨榜"] = fmt(self.user_msg_count)
        rankings["字数榜"] = fmt(self.user_char_count)

        sorted_avg: list[tuple[str | int, float]] = sorted(
            self.user_char_per_msg.items(), key=lambda x: x[1], reverse=True
        )[: config.analysis.contributor_top_n]
        rankings["长文王"] = [
            (self.get_name(uin), f"{avg:.1f}字/条") for uin, avg in sorted_avg
        ]

        rankings["图片狂魔"] = fmt(self.user_image_count)
        rankings["合并转发王"] = fmt(self.user_forward_count)
        rankings["回复狂"] = fmt(self.user_reply_count)
        rankings["被回复最多"] = fmt(self.user_replied_count)
        rankings["艾特狂"] = fmt(self.user_at_count)
        rankings["被艾特最多"] = fmt(self.user_ated_count)
        rankings["表情帝"] = fmt(self.user_emoji_count)
        rankings["链接分享王"] = fmt(self.user_link_count)
        rankings["深夜党"] = fmt(self.user_night_count)
        rankings["早起鸟"] = fmt(self.user_morning_count)
        rankings["复读机"] = fmt(self.user_repeat_count)

        return rankings

    def export_json(self) -> dict[str, Any]:
        """导出 JSON 格式结果（包含 UIN 信息）

        Returns:
            完整的分析结果字典
        """
        result: dict[str, Any] = {
            "chatName": self.chat_name,
            "messageCount": len(self.messages),
            "topWords": [
                {
                    "word": word,
                    "freq": freq,
                    "contributors": [
                        {
                            "name": self.get_name(uin),
                            "uin": str(uin),
                            "count": count,
                        }
                        for uin, count in self.word_contributors[word].most_common(
                            config.analysis.contributor_top_n
                        )
                    ],
                    "samples": self.word_samples.get(word, [])[
                        : config.analysis.sample_count
                    ],
                }
                for word, freq in self.get_top_words()
            ],
            "rankings": {},
            "hourDistribution": {
                str(h): self.hour_distribution.get(h, 0) for h in range(24)
            },
        }

        # 趣味榜单（包含 UIN）
        def fmt_with_uin(
            counter: Counter[str | int], top_n: int = config.analysis.contributor_top_n
        ) -> list[dict[str, Any]]:
            return [
                {"name": self.get_name(uin), "uin": str(uin), "value": count}
                for uin, count in counter.most_common(top_n)
            ]

        result["rankings"]["话痨榜"] = fmt_with_uin(self.user_msg_count)
        result["rankings"]["字数榜"] = fmt_with_uin(self.user_char_count)

        # 长文王特殊处理
        sorted_avg_export: list[tuple[str | int, float]] = sorted(
            self.user_char_per_msg.items(), key=lambda x: x[1], reverse=True
        )[: config.analysis.contributor_top_n]
        result["rankings"]["长文王"] = [
            {"name": self.get_name(uin), "uin": str(uin), "value": f"{avg:.1f}字/条"}
            for uin, avg in sorted_avg_export
        ]

        result["rankings"]["图片狂魔"] = fmt_with_uin(self.user_image_count)
        result["rankings"]["合并转发王"] = fmt_with_uin(self.user_forward_count)
        result["rankings"]["回复狂"] = fmt_with_uin(self.user_reply_count)
        result["rankings"]["被回复最多"] = fmt_with_uin(self.user_replied_count)
        result["rankings"]["艾特狂"] = fmt_with_uin(self.user_at_count)
        result["rankings"]["被艾特最多"] = fmt_with_uin(self.user_ated_count)
        result["rankings"]["表情帝"] = fmt_with_uin(self.user_emoji_count)
        result["rankings"]["链接分享王"] = fmt_with_uin(self.user_link_count)
        result["rankings"]["深夜党"] = fmt_with_uin(self.user_night_count)
        result["rankings"]["早起鸟"] = fmt_with_uin(self.user_morning_count)
        result["rankings"]["复读机"] = fmt_with_uin(self.user_repeat_count)

        return result
