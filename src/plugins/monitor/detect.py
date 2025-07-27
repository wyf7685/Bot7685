from datetime import datetime, timedelta

import httpx
from nonebot import logger
from nonebot_plugin_alconna import UniMessage
from nonebot_plugin_chatrecorder import get_message_records
from nonebot_plugin_uninfo import Session
from nonebot_plugin_uninfo.target import to_target
from pydantic import BaseModel

from .config import config

PROMPT_DETECT = """\
你是一个专业的内容审核助手，负责分析群组聊天记录中是否包含敏感话题。

请仔细分析以下群组对话记录，检测是否包含以下敏感内容：

1. **政治敏感内容**：涉及政治人物、政治事件、政治观点争议等
2. **暴力威胁**：包含暴力威胁、恐吓、伤害他人的言论
3. **仇恨言论**：基于种族、性别、宗教、性取向等的歧视性言论
4. **色情内容**：包含色情、性暗示、不当性内容
5. **违法活动**：涉及毒品、赌博、诈骗、非法交易等违法行为
6. **个人信息泄露**：包含他人隐私信息、身份证号、手机号等敏感个人信息
7. **恶意传播**：恶意传播谣言、虚假信息、恶意中伤他人
8. **自杀自残**：包含自杀、自残相关的内容或引导
9. **网络欺凌**：恶意骚扰、网络霸凌、人身攻击
10. **商业广告**：未经授权的商业推广、spam内容

分析要求：
- 考虑上下文语境，避免误判正常讨论
- 重点关注明显的敏感表达和潜在风险
- 对于模糊边界的内容要谨慎判断
- 如果多条消息组合起来形成敏感内容，也需要识别

请严格按照以下JSON格式返回分析结果：
{
  "block": true/false,
  "reason": "如果需要拦截，请详细说明检测到的敏感内容类型和具体原因；如果不需要拦截，返回空字符串"
}

注意：
- 只返回JSON格式，不要添加任何其他文字
- reason字段要简洁明确，指出具体的敏感内容类型
- 对于正常的日常聊天、学术讨论、新闻分享等，应返回block: false
"""  # noqa: E501


class LLMResponse(BaseModel):
    block: bool
    reason: str = ""


def format_messages(messages: list[tuple[int, str]]) -> str:
    return "\n".join(
        f"<msg seq={seq} user={user_id}>\n{message}\n</msg seq={seq} user={user_id}>"
        for seq, (user_id, message) in enumerate(messages, 1)
    )


async def call_llm(content: str) -> LLMResponse | None:
    messages = [
        {"role": "system", "content": PROMPT_DETECT},
        {"role": "user", "content": content},
    ]
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{config.llm.endpoint.rstrip('/')}/chat/completions",
            json={"model": config.llm.model, "messages": messages},
            headers={"Authorization": f"Bearer {config.llm.api_key}"},
        )
        data = response.raise_for_status().json()
    resp: str = data["choices"][0]["message"]["content"]
    maybe_json = resp[resp.find("{") : resp.rfind("}") + 1]

    try:
        return LLMResponse.model_validate_json(maybe_json)
    except ValueError:
        logger.warning(f"解析LLM响应失败: {maybe_json}")
        return None


last_detect: dict[str, datetime] = {}


async def detect(session: Session) -> None:
    now = datetime.now()
    if (last := last_detect.get(session.scene.id)) and (
        now - last < timedelta(seconds=60)
    ):
        logger.debug(f"会话 {session.scene.id} 检测频率过高，跳过")
        return

    time_stop = last_detect[session.scene.id] = now
    time_start = time_stop - timedelta(seconds=config.record_delta)
    records = await get_message_records(
        session=session,
        filter_self_id=True,
        filter_adapter=True,
        filter_scope=True,
        filter_scene=True,
        filter_user=False,
        time_start=time_start,
        time_stop=time_stop,
    )
    messages = [(record.session_persist_id, record.plain_text) for record in records]

    if (result := await call_llm(format_messages(messages))) is None:
        return

    if not result.block:
        logger.debug(f"会话 {session.scene.id} 检测结果: 无敏感内容")
        return

    logger.warning(
        f"会话 {session.scene.id} 检测到敏感内容: {result.reason or '未提供具体原因'}"
    )
    await (
        UniMessage.at(session.user.id)
        .text(config.warning_msg.format(reason=result.reason))
        .send(target=to_target(session))
    )
