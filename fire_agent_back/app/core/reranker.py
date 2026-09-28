"""
Rerank 精排 — 阿里 DashScope text-rerank 原生 API（P1 #9）

- 使用 LLM_API_KEY（与 Embedding 同源，恒阿里百炼，不随 LLM Provider 切换）；
- (query, documents) 维度 5 分钟缓存，避免重复计费；
- 任何失败（未配 Key / 网络异常 / 模型 404 / 超时）返回 None，调用方降级为
  RRF 融合原序，不阻断检索链路。
"""
import time
import logging

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

_RERANK_URL = "https://dashscope.aliyuncs.com/api/v1/services/rerank/text-rerank/text-rerank"
_TIMEOUT = 15.0

# 进程内缓存：key=(query, documents元组) -> (时间戳, results)
_CACHE: dict = {}
_CACHE_TTL = 300  # 5 分钟


def rerank(query: str, documents: list[str], top_n: int | None = None) -> list[dict] | None:
    """调用 DashScope text-rerank 对候选文档按相关度精排

    Args:
        query: 查询文本
        documents: 候选文档内容列表（与调用方候选池顺序一一对应）
        top_n: 返回前 N 条（默认全部）

    Returns:
        [{"index": int, "relevance_score": float}, ...]（按相关度降序）；
        关闭/未配 Key/失败时返回 None，调用方降级。
    """
    if not settings.RERANK_ENABLED:
        return None
    api_key = settings.LLM_API_KEY
    if not api_key or not documents:
        return None
    top_n = top_n or len(documents)

    cache_key = (query, tuple(documents))
    cached = _CACHE.get(cache_key)
    if cached and time.monotonic() - cached[0] < _CACHE_TTL:
        return cached[1]

    try:
        resp = httpx.post(
            _RERANK_URL,
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": settings.RERANK_MODEL,
                "input": {"query": query, "documents": documents},
                "parameters": {"return_documents": False, "top_n": top_n},
            },
            timeout=_TIMEOUT,
        )
        if resp.status_code != 200:
            logger.warning("rerank 失败 HTTP %s: %s", resp.status_code, resp.text[:120])
            return None
        results = resp.json().get("output", {}).get("results")
        if not isinstance(results, list):
            logger.warning("rerank 响应格式异常: %s", str(resp.json())[:120])
            return None
        out = [{"index": int(r["index"]), "relevance_score": float(r.get("relevance_score", 0.0))}
               for r in results if isinstance(r, dict) and "index" in r]
        _CACHE[cache_key] = (time.monotonic(), out)
        # 简单防膨胀：缓存超过 256 条时清空最旧的一半
        if len(_CACHE) > 256:
            for k in sorted(_CACHE, key=lambda k: _CACHE[k][0])[:128]:
                _CACHE.pop(k, None)
        return out
    except Exception as e:
        logger.warning("rerank 调用异常，降级 RRF 原序: %s", e)
        return None
