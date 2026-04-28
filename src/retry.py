"""
指数退避重试工具

为 LLM 调用提供生产级可靠性保障：
  - 指数退避（Exponential Backoff）：延迟按 base * 2^attempt 增长，避免持续轰炸服务
  - 随机抖动（Jitter）：在基础延迟上叠加 ±20% 随机量，缓解"惊群效应"
  - 错误分类：区分"可重试"（限流/服务端/超时）与"不可重试"（认证/参数错误）
    认证失败重试无意义，参数错误重试不会有不同结果

设计模式：
  RetryConfig dataclass 存储重试策略，与 LLMClient 解耦，可按场景定制配置。
  with_retry() 是无状态工具函数，接受任意 callable，不依赖 LLM 具体实现。

面试话术：
  "我在 LLM 调用层加了指数退避重试，1s→2s→4s 三次重试，
   同时叠加 ±20% jitter 避免多个并发请求同时重试打垮服务，
   并对 4xx 认证/参数错误做了快失败处理，不浪费重试次数。"
"""

from __future__ import annotations

import time
import random
import logging
from dataclasses import dataclass, field
from typing import Callable, Any, Type

logger = logging.getLogger(__name__)


# ── 重试配置 ──────────────────────────────────────────────────────────────────

@dataclass
class RetryConfig:
    """
    重试策略配置，可按场景定制。

    delay 公式：min(base_delay * 2^attempt, max_delay) * (1 ± jitter_factor)

    Attributes:
        max_retries:    最多重试次数（不含首次调用，总调用次数 = max_retries + 1）
        base_delay:     首次重试等待秒数（之后翻倍）
        max_delay:      单次等待上限（防止退避无限增长）
        jitter_factor:  随机抖动幅度（0.2 表示 ±20%）
        retryable_exceptions: 触发重试的异常类型元组（运行时填充，见各客户端）
        non_retryable_status: HTTP 状态码集合（命中则立即抛出，不重试）
    """
    max_retries:          int   = 3
    base_delay:           float = 1.0
    max_delay:            float = 16.0
    jitter_factor:        float = 0.2
    non_retryable_status: frozenset = field(
        default_factory=lambda: frozenset({400, 401, 403, 404, 422})
    )

    def delay_for(self, attempt: int) -> float:
        """
        计算第 attempt 次重试的等待时间（attempt 从 0 开始）。
        示例（base=1, max=16, jitter=0.2）：
          attempt=0 → ~1s, attempt=1 → ~2s, attempt=2 → ~4s
        """
        base  = min(self.base_delay * (2 ** attempt), self.max_delay)
        noise = base * self.jitter_factor * (2 * random.random() - 1)  # ±jitter
        return max(0.0, base + noise)


# 默认配置：用于 LLM 调用
DEFAULT_RETRY = RetryConfig(max_retries=3, base_delay=1.0, max_delay=16.0)

# 轻量配置：用于 Archetype 分类等低成本调用
LIGHT_RETRY = RetryConfig(max_retries=2, base_delay=0.5, max_delay=4.0)


# ── 重试执行器 ─────────────────────────────────────────────────────────────────

def with_retry(
    func: Callable[[], Any],
    config: RetryConfig = DEFAULT_RETRY,
    retryable_exceptions: tuple[Type[Exception], ...] = (Exception,),
    label: str = "LLM call",
) -> Any:
    """
    带指数退避的重试执行器。

    Args:
        func:                  无参数的 callable（用 lambda 包裹带参函数）
        config:                重试策略配置
        retryable_exceptions:  触发重试的异常类型（其他异常立即抛出）
        label:                 日志前缀，用于区分不同调用场景

    Returns:
        func() 的返回值

    Raises:
        最后一次重试仍失败时，抛出原始异常

    Example:
        result = with_retry(
            lambda: client.chat(prompt),
            retryable_exceptions=(RateLimitError, APITimeoutError),
            label="evaluate",
        )
    """
    last_error: Exception | None = None

    for attempt in range(config.max_retries + 1):
        try:
            return func()

        except retryable_exceptions as e:
            last_error = e

            # 检查是否为不可重试的 HTTP 状态码（认证错误、参数错误等）
            status = _extract_status(e)
            if status in config.non_retryable_status:
                logger.debug(f"[{label}] HTTP {status} 不可重试，直接抛出：{e}")
                raise

            if attempt == config.max_retries:
                # 已耗尽所有重试次数
                logger.warning(
                    f"[{label}] 已重试 {config.max_retries} 次，全部失败：{type(e).__name__}: {e}"
                )
                raise

            delay = config.delay_for(attempt)
            logger.warning(
                f"[{label}] 第 {attempt + 1}/{config.max_retries} 次重试，"
                f"{delay:.1f}s 后重试（{type(e).__name__}: {e}）"
            )
            print(f"  ⏳ [{label}] 请求失败，{delay:.1f}s 后重试"
                  f"（{attempt + 1}/{config.max_retries}）...")
            time.sleep(delay)

        except Exception:
            # 不在 retryable_exceptions 中的异常：快失败，不浪费重试机会
            raise

    # 理论上不会到达此处
    raise last_error  # type: ignore


# ── 内部工具 ──────────────────────────────────────────────────────────────────

def _extract_status(exc: Exception) -> int | None:
    """从异常中提取 HTTP 状态码（兼容 anthropic / requests 两种异常体系）"""
    # anthropic SDK：APIStatusError.status_code
    if hasattr(exc, "status_code"):
        return exc.status_code
    # requests：response.status_code
    if hasattr(exc, "response") and hasattr(exc.response, "status_code"):
        return exc.response.status_code
    return None
