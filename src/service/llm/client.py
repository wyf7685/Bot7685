from __future__ import annotations

import asyncio
import json
from typing import Any, TypeVar

import httpx
from nonebot.log import logger
from nonebot.utils import escape_tag
from pydantic import BaseModel

from .config import LLMConfig
from .exceptions import (
    CircuitBreakerOpenError,
    LLMJSONParseError,
    LLMResponseError,
    LLMRetriesExhaustedError,
)
from .resilience import CircuitBreaker, GlobalRateLimiter
from .schema import Message, dump_messages

T = TypeVar("T", bound=BaseModel)


class LLMClient:
    """OpenAI 兼容的 LLM 客户端，支持重试、超时、结构化输出。"""

    def __init__(self, config: LLMConfig) -> None:
        self._config = config
        self._client: httpx.AsyncClient | None = None
        self._circuit_breaker = CircuitBreaker(
            name="llm",
            failure_threshold=config.max_retries + 2,
            recovery_timeout=60.0,
        )
        GlobalRateLimiter.get_instance(config.max_concurrent)

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=self._config.timeout)
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def chat_completion(
        self,
        *messages: Message,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        response_format: dict[str, Any] | None = None,
    ) -> str:
        """调用 Chat Completion API 并返回纯文本结果。

        Args:
            *messages: 类型化的消息序列
            model: 可选的模型覆盖
            temperature: 温度参数
            max_tokens: 最大生成 token 数
            response_format: OpenAI JSON Schema 格式的响应约束

        Returns:
            str: LLM 返回的文本内容
        """
        content = await self._raw_completion(
            dump_messages(*messages),
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format=response_format,
        )
        text = content.get("choices", [{}])[0].get("message", {}).get("content", "")
        return text.strip()

    async def chat_completion_json(
        self,
        *messages: Message,
        response_model: type[T],
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> T:
        """带 Pydantic 模型约束的结构化输出。

        内部通过 model_json_schema() 生成 JSON Schema，
        使用 model_validate() 验证并解析结果。

        Args:
            *messages: 类型化的消息序列
            response_model: 期望的 Pydantic 模型类型
            model: 可选的模型覆盖
            temperature: 温度参数
            max_tokens: 最大生成 token 数

        Returns:
            T: response_model 的实例
        """
        schema = response_model.model_json_schema()
        response_format = {
            "type": "json_schema",
            "json_schema": {
                "name": response_model.__name__,
                "schema": schema,
            },
        }

        raw_content = await self.chat_completion(
            *messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format=response_format,
        )

        parsed = self._parse_json(raw_content)
        return response_model.model_validate(parsed)

    async def _raw_completion(
        self,
        messages: list[dict[str, str]],
        model: str | None,
        temperature: float,
        max_tokens: int,
        response_format: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """带重试和熔断器的原始 API 调用。"""
        config = self._config
        cb = self._circuit_breaker
        last_exc: Exception | None = None

        for attempt in range(1, config.max_retries + 1):
            if not cb.allow_request():
                raise CircuitBreakerOpenError("LLM 熔断器已打开，拒绝请求")

            try:
                async with GlobalRateLimiter.get_instance().semaphore:
                    payload: dict[str, Any] = {
                        "model": model or config.model,
                        "messages": messages,
                        "max_tokens": max_tokens,
                        "temperature": temperature,
                    }
                    if response_format is not None:
                        payload["response_format"] = response_format

                    headers = {
                        "Authorization": f"Bearer {config.api_key}",
                        "Content-Type": "application/json",
                    }

                    client = await self._get_client()
                    resp = await client.post(
                        f"{config.base_url.rstrip('/')}/chat/completions",
                        json=payload,
                        headers=headers,
                    )

                    if resp.status_code != 200:
                        if response_format is not None and self._is_format_unsupported(
                            resp.text
                        ):
                            logger.opt(colors=True).warning(
                                "Provider 不支持 <y>response_format</>，降级重试"
                            )
                            return await self._raw_completion(
                                messages,
                                model=model,
                                temperature=temperature,
                                max_tokens=max_tokens,
                                response_format=None,
                            )
                        raise LLMResponseError(
                            f"API 错误 ({resp.status_code}): {resp.text[:200]}"
                        )

                    cb.record_success()
                    return resp.json()

            except LLMResponseError, CircuitBreakerOpenError:
                raise
            except Exception as e:
                cb.record_failure()
                last_exc = e
                logger.opt(colors=True).warning(
                    f"LLM 请求失败 (第 <y>{attempt}</> 次): {escape_tag(str(e))}"
                )

            if attempt < config.max_retries:
                await asyncio.sleep(config.retry_backoff * attempt)

        raise LLMRetriesExhaustedError(
            f"LLM 请求全部重试失败: {last_exc}"
        ) from last_exc

    @staticmethod
    def _is_format_unsupported(error_text: str) -> bool:
        text = error_text.lower()
        patterns = [
            "response_format",
            "json_schema",
            "unexpected keyword argument",
            "extra fields not permitted",
            "not support",
            "not supported",
        ]
        return any(p in text for p in patterns)

    @staticmethod
    def _parse_json(text: str) -> dict[str, Any]:
        """从 LLM 返回的文本中解析 JSON，处理可能的 markdown 包裹。"""
        text = text.strip()

        if text.startswith("```"):
            lines = text.split("\n")
            start = 1
            end = len(lines) - 1
            if lines[-1].strip() == "```":
                end -= 1
            text = "\n".join(lines[start:end]).strip()

        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            raise LLMJSONParseError(
                f"无法解析 LLM 返回的 JSON: {e}\n原始内容: {text[:500]}"
            ) from e
