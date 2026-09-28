"""
统一 LLM 调用层 — 重试 / 熔断 / 多 Provider 降级 / token 记账 / 结构化输出

所有 Agent / Service 的 LLM 调用统一走本模块（取代直接 llm.invoke），
保证生产可用性：
1. 重试：限流 / 超时 / 连接类异常指数退避重试（单 Provider 最多 3 次，1s/2s/4s）
2. 熔断：单 Provider 连续失败 ≥3 次则熔断 60s，期间直接跳过
3. 降级链：当前激活 Provider → 其余可用 Provider → 返回 None（调用方走规则兜底）
4. 审计：每次调用返回 token 用量与实际使用的 Provider，供 agent steps 落库展示
"""
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Optional, Type, TypeVar

from pydantic import BaseModel

from app.core.config import settings

T = TypeVar("T", bound=BaseModel)

# 降级链顺序：激活 Provider 优先，其余按固定顺序补充
_ALL_PROVIDERS = ("aliyun", "amd", "ollama")


def _provider_chain() -> list[str]:
    active = settings.ACTIVE_LLM_PROVIDER or "aliyun"
    return [active] + [p for p in _ALL_PROVIDERS if p != active]


def _build_llm(provider: str, **kwargs):
    """构造指定 Provider 的 LLM 实例（复用 core/llm.py 的构建函数；未配置返回 None）"""
    from app.core import llm as _llm_mod
    if provider == "amd":
        return _llm_mod._get_amd_llm(**kwargs)
    if provider == "ollama":
        return _llm_mod._get_ollama_llm(**kwargs)
    return _llm_mod._get_aliyun_llm(**kwargs)


def _resolve_model(provider: str, kwargs: dict) -> str:
    """解析本次调用实际使用的模型名（显式指定优先，否则取该 Provider 的默认配置）"""
    if kwargs.get("model"):
        return str(kwargs["model"])
    if provider == "amd":
        return settings.AMD_MODEL or "DeepSeek-V4-Flash"
    if provider == "ollama":
        return settings.OLLAMA_MODEL or ""
    return settings.LLM_MODEL or ""


# ===================== 简单熔断器（内存态，进程内共享） =====================

class _Breaker:
    """连续失败计数熔断：失败达阈值进入 open 状态，冷却期后放行一次探测"""

    def __init__(self, threshold: int = 3, cooldown: float = 60.0):
        self.threshold = threshold
        self.cooldown = cooldown
        self.consecutive_failures = 0
        self.opened_at: float = 0.0
        self._lock = threading.Lock()

    def allow(self) -> bool:
        with self._lock:
            if self.consecutive_failures < self.threshold:
                return True
            return (time.monotonic() - self.opened_at) >= self.cooldown

    def record_success(self) -> None:
        with self._lock:
            self.consecutive_failures = 0

    def record_failure(self) -> None:
        with self._lock:
            self.consecutive_failures += 1
            if self.consecutive_failures >= self.threshold:
                self.opened_at = time.monotonic()


_BREAKERS: dict[str, _Breaker] = {}
_BREAKERS_LOCK = threading.Lock()


def breaker_status() -> dict:
    """熔断器快照（供「系统能力」面板展示；线程安全只读拷贝）"""
    with _BREAKERS_LOCK:
        snap = {}
        for provider, b in _BREAKERS.items():
            opened = b.consecutive_failures >= b.threshold
            remaining = 0.0
            if opened:
                remaining = max(0.0, b.cooldown - (time.monotonic() - b.opened_at))
            snap[provider] = {
                "open": opened,
                "consecutive_failures": b.consecutive_failures,
                "threshold": b.threshold,
                "cooldown": b.cooldown,
                "remaining": round(remaining, 1),
            }
        return snap


def _breaker(provider: str) -> _Breaker:
    with _BREAKERS_LOCK:
        if provider not in _BREAKERS:
            _BREAKERS[provider] = _Breaker()
        return _BREAKERS[provider]


# ===================== 调用结果 =====================

@dataclass
class LLMResult:
    """LLM 调用结果（text 为响应文本；tokens/provider/model 供审计）"""
    text: str
    provider: str = ""
    tokens: dict = field(default_factory=dict)
    degraded: bool = False  # 是否发生了跨 Provider 降级
    model: str = ""         # 实际使用的模型名（详细展示用，如 qwen-max）


def _extract_tokens(resp) -> dict:
    """从 LangChain AIMessage 提取 token 用量（兼容不同 provider 返回）"""
    try:
        meta = getattr(resp, "response_metadata", None) or {}
        usage = meta.get("token_usage") or {}
        if not usage:
            usage = getattr(resp, "usage_metadata", None) or {}
        out = {}
        for k in ("prompt_tokens", "completion_tokens", "total_tokens"):
            v = usage.get(k)
            if isinstance(v, (int, float)):
                out[k] = int(v)
        return out
    except Exception:
        return {}


def _extract_text(resp) -> str:
    content = getattr(resp, "content", None)
    if isinstance(content, str):
        return content
    # 多模态/分块内容兜底
    if isinstance(content, list):
        return "".join(c.get("text", "") for c in content if isinstance(c, dict))
    return str(resp)


def _retryable(exc: Exception) -> bool:
    """判定异常是否可重试（限流/超时/连接类）；鉴权、参数错误不重试直接换 Provider"""
    import openai
    return isinstance(exc, (
        openai.RateLimitError,
        openai.APITimeoutError,
        openai.APIConnectionError,
        openai.InternalServerError,
    ))


_RETRY_DELAYS = (1.0, 2.0, 4.0)


# ===================== 对外接口 =====================

def invoke_llm(
    prompt: str,
    *,
    temperature: float | None = None,
    max_tokens: int | None = None,
    model: str | None = None,
    enable_thinking: bool | None = None,
) -> LLMResult | None:
    """
    统一 LLM 文本调用入口。

    成功返回 LLMResult；所有 Provider 均失败返回 None（调用方自行走规则兜底）。
    enable_thinking=False：关闭思考型模型的 reasoning（防长思考吃满 max_tokens 导致正文为空）。
    """
    active = settings.ACTIVE_LLM_PROVIDER or "aliyun"
    kwargs = {}
    if temperature is not None:
        kwargs["temperature"] = temperature
    if max_tokens is not None:
        kwargs["max_tokens"] = max_tokens
    if model is not None:
        kwargs["model"] = model
    if enable_thinking is not None:
        kwargs["enable_thinking"] = enable_thinking

    for provider in _provider_chain():
        breaker = _breaker(provider)
        if not breaker.allow():
            continue
        llm = _build_llm(provider, **kwargs)
        if llm is None:  # 该 Provider 未配置，跳过
            continue
        last_exc: Exception | None = None
        for attempt, delay in enumerate((None,) + _RETRY_DELAYS):
            if delay:
                time.sleep(delay)
            try:
                resp = llm.invoke(prompt)
                breaker.record_success()
                return LLMResult(
                    text=_extract_text(resp),
                    provider=provider,
                    tokens=_extract_tokens(resp),
                    degraded=(provider != active),
                    model=_resolve_model(provider, kwargs),
                )
            except Exception as e:
                last_exc = e
                if not _retryable(e):
                    break  # 不可重试 → 直接换下一个 Provider
        breaker.record_failure()
    return None


def invoke_structured(
    prompt: str,
    schema: Type[T],
    *,
    temperature: float | None = None,
    max_tokens: int | None = None,
    fallback: Optional[Callable[[str], Optional[T]]] = None,
) -> tuple[Optional[T], Optional[LLMResult]]:
    """
    统一 LLM 结构化输出入口。

    优先 with_structured_output（function calling）；Provider 不支持或调用失败时，
    降级为文本调用 + fallback(text) 解析。两级都失败返回 (None, None)。

    Args:
        fallback: 文本解析兜底函数（输入原始文本，返回 schema 实例或 None）
    Returns:
        (结构化对象, 调用元信息)；对象可能来自结构化输出或 fallback 解析
    """
    active = settings.ACTIVE_LLM_PROVIDER or "aliyun"
    kwargs = {}
    if temperature is not None:
        kwargs["temperature"] = temperature
    if max_tokens is not None:
        kwargs["max_tokens"] = max_tokens

    # —— 第一级：结构化输出 ——
    for provider in _provider_chain():
        breaker = _breaker(provider)
        if not breaker.allow():
            continue
        llm = _build_llm(provider, **kwargs)
        if llm is None:
            continue
        try:
            structured = llm.with_structured_output(schema)
        except Exception:
            break  # 当前栈不支持结构化 → 直接走文本降级
        for delay in (None,) + _RETRY_DELAYS:
            if delay:
                time.sleep(delay)
            try:
                obj = structured.invoke(prompt)
                breaker.record_success()
                if obj is not None:
                    return obj, LLMResult(
                        text="",
                        provider=provider,
                        degraded=(provider != active),
                        model=_resolve_model(provider, kwargs),
                    )
                break  # 空响应 → 换下一个 Provider
            except Exception as e:
                if not _retryable(e):
                    break
        breaker.record_failure()

    # —— 第二级：文本调用 + fallback 解析 ——
    if fallback is not None:
        res = invoke_llm(prompt, temperature=temperature, max_tokens=max_tokens)
        if res is not None:
            try:
                obj = fallback(res.text)
                if obj is not None:
                    return obj, res
            except Exception:
                pass
    return None, None


def stream_llm(
    prompt: str,
    *,
    temperature: float | None = None,
    max_tokens: int | None = None,
    model: str | None = None,
    enable_thinking: bool | None = None,
):
    """统一 LLM 流式文本生成入口（P2#18，与 invoke_llm 同级的流式通道）。

    逐 chunk 产出事件字典：
      {"type": "delta", "text": str}                                        增量内容（0~n 条）
      {"type": "meta",  "provider": str, "degraded": bool, "tokens": dict}  成功终态
      {"type": "error", "message": str}                                     失败终态（所有通道不可用）

    复用 invoke_llm 的 Provider 降级链 + 熔断器 + 重试；差别在于：仅在尚未产出
    任何内容前才允许重试/换 Provider（半截内容无法跨通道续写），已产出的 delta
    是否丢弃重试由调用方决定。
    enable_thinking=False：关闭思考型模型的 reasoning（同 invoke_llm，防长思考
    吃满 max_tokens 导致正文为空）。
    """
    active = settings.ACTIVE_LLM_PROVIDER or "aliyun"
    kwargs = {}
    if temperature is not None:
        kwargs["temperature"] = temperature
    if max_tokens is not None:
        kwargs["max_tokens"] = max_tokens
    if model is not None:
        kwargs["model"] = model
    if enable_thinking is not None:
        kwargs["enable_thinking"] = enable_thinking

    for provider in _provider_chain():
        breaker = _breaker(provider)
        if not breaker.allow():
            continue
        llm = _build_llm(provider, **kwargs)
        if llm is None:
            continue
        produced = False
        last_exc: Exception | None = None
        for delay in (None,) + _RETRY_DELAYS:
            if delay:
                time.sleep(delay)
            try:
                meta = {"type": "meta", "provider": provider,
                        "degraded": provider != active, "tokens": {},
                        "model": _resolve_model(provider, kwargs)}
                for chunk in llm.stream(prompt):
                    text = _extract_text(chunk)
                    if text:
                        produced = True
                        yield {"type": "delta", "text": text}
                    usage = _extract_tokens(chunk)
                    if usage:
                        meta["tokens"] = usage
                breaker.record_success()
                yield meta
                return
            except Exception as e:
                last_exc = e
                if produced or not _retryable(e):
                    break  # 已产出内容（无法跨通道续写）或不可重试 → 换下一个 Provider
        breaker.record_failure()
    yield {"type": "error", "message": str(last_exc or "所有 LLM 通道均不可用")[:200]}
