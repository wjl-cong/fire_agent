"""
Langfuse 观测接入（P2#12）— 可选回调，未启用/未部署自动降级纯日志

- LangChain CallbackHandler 接入：LangGraph config 携带 callbacks 后，
  所有节点内 LLM 调用的 trace/span/token 自动上报 Langfuse
- trace_id 贯穿：session_id = thread_id（task-{id}），metadata 携带 task_id，
  可与系统日志/SSE 事件按任务关联
- 边界：Langfuse 未部署（私服不在线）不影响业务执行 —— SDK 上报失败仅
  打点丢失；本模块导入失败或未配置密钥时返回 None（无 callbacks）
"""
from app.core.config import settings

_handler_disabled = False  # SDK 导入/初始化失败后置位，进程内不再重试


def build_callback_config(task_id: int | None = None, thread_id: str | None = None) -> dict | None:
    """构造 LangGraph 运行配置中的观测字段；未启用返回 None（调用方不加 callbacks）

    Returns:
        None 或 {"callbacks": [handler], "metadata": {...}, "tags": [...]}
    """
    global _handler_disabled
    if not settings.LANGFUSE_ENABLED:
        return None
    if not (settings.LANGFUSE_PUBLIC_KEY and settings.LANGFUSE_SECRET_KEY):
        return None  # 未配置密钥 → 纯日志降级
    if _handler_disabled:
        return None
    try:
        from langfuse.langchain import CallbackHandler

        handler = CallbackHandler(
            public_key=settings.LANGFUSE_PUBLIC_KEY,
            secret_key=settings.LANGFUSE_SECRET_KEY,
            host=settings.LANGFUSE_HOST,
        )
        if thread_id:
            try:
                handler.session_id = thread_id  # Langfuse 会话维度贯穿同一任务
            except Exception:
                pass
        metadata = {"service": "fire_agent"}
        if task_id is not None:
            metadata["task_id"] = task_id
        return {"callbacks": [handler], "metadata": metadata, "tags": ["fire-agent"]}
    except Exception:
        _handler_disabled = True
        return None
