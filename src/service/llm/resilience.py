"""熔断器与全局限流器，复用自 AstrBot 插件。"""

from __future__ import annotations

import asyncio
import enum
import time


class _CircuitState(enum.Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    """按调用方（如 provider 名称）粒度的熔断器。"""

    def __init__(
        self,
        name: str = "default",
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
        half_open_max_calls: int = 1,
    ) -> None:
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_calls = half_open_max_calls

        self._state = _CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time: float = 0
        self._half_open_calls = 0

    @property
    def state(self) -> _CircuitState:
        if (
            self._state == _CircuitState.OPEN
            and time.monotonic() - self._last_failure_time >= self.recovery_timeout
        ):
            self._state = _CircuitState.HALF_OPEN
            self._half_open_calls = 0
        return self._state

    def allow_request(self) -> bool:
        st = self.state
        if st == _CircuitState.CLOSED:
            return True
        if st == _CircuitState.HALF_OPEN:
            if self._half_open_calls < self.half_open_max_calls:
                self._half_open_calls += 1
                return True
            return False
        return False

    def record_success(self) -> None:
        self._failure_count = 0
        self._state = _CircuitState.CLOSED

    def record_failure(self) -> None:
        self._failure_count += 1
        self._last_failure_time = time.monotonic()
        if (
            self._state == _CircuitState.HALF_OPEN
            or self._failure_count >= self.failure_threshold
        ):
            self._state = _CircuitState.OPEN


class GlobalRateLimiter:
    """全局异步信号量限流器，单例模式。"""

    _instance: GlobalRateLimiter | None = None

    def __init__(self, max_concurrent: int) -> None:
        self.semaphore = asyncio.Semaphore(max_concurrent)

    @classmethod
    def get_instance(cls, max_concurrent: int = 5) -> GlobalRateLimiter:
        if cls._instance is None:
            cls._instance = cls(max_concurrent)
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """重置单例（用于测试或重新配置）。"""
        cls._instance = None
