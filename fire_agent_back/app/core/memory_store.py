"""
用户分析偏好长期记忆（P2#15）— LangGraph PostgresStore

- 存储：业务库同实例的 LangGraph Store 表（setup() 幂等建表，JSONB，无需 pgvector）
- Namespace：("prefs", "user-{user_id}")，key="analysis"，按 user_id 严格隔离
- 写入：任务完成后从查询文本提取偏好（常查州市/关注时段），确定性合并进旧偏好
  （不引入 langmem 依赖，保护 langchain-core 版本锁）
- 读取：ReportAgent 生成报告时注入偏好上下文，报告更贴合用户辖区
- 边界：任何异常静默跳过不阻断主流程；PREFERENCES_ENABLED=False 整体关闭；
  连接模式与 checkpointer.py 一致（psycopg 非线程安全，每调用方独享连接）
"""
import threading

from pydantic import BaseModel, Field

from app.core.config import settings

_setup_lock = threading.Lock()
_setup_done = False
_store_disabled = False  # 一旦探测失败，后续直接跳过，避免每次任务都重试连接


class _PrefExtract(BaseModel):
    """偏好提取 Schema（invoke_structured 用）"""
    cities: list[str] = Field(default_factory=list, description="查询中提到的云南州市全名")
    period: str = Field("", description="关注时段（如 2026年4月 / 春季 / 近3年），无则空串")


def _conninfo() -> str:
    """复用 checkpointer 的连接串归一化（SQLAlchemy URL → psycopg3 URL）"""
    from app.core.checkpointer import _conninfo as _ck_conninfo
    return _ck_conninfo()


def create_store():
    """创建新的 PostgresStore 实例（每调用方独享连接）；环境不具备返回 None"""
    global _setup_done, _store_disabled
    if not _store_disabled:
        conn = None
        try:
            import psycopg
            from langgraph.store.postgres import PostgresStore

            conn = psycopg.connect(_conninfo(), autocommit=True)
            store = PostgresStore(conn)
            with _setup_lock:
                if not _setup_done:
                    store.setup()
                    _setup_done = True
            return store
        except Exception:
            _store_disabled = True
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass
    return None


def get_user_preferences(user_id: int) -> dict:
    """读取用户偏好；关闭/不可用/无记录返回 {}（绝不抛异常）"""
    if not settings.PREFERENCES_ENABLED or not user_id:
        return {}
    store = create_store()
    if store is None:
        return {}
    try:
        item = store.get(("prefs", f"user-{user_id}"), "analysis")
        return dict(item.value) if item and item.value else {}
    except Exception:
        return {}


def record_task_interests(user_id: int, query: str) -> None:
    """任务完成后提取并合并用户偏好（worker 后台线程调用；失败静默）"""
    if not settings.PREFERENCES_ENABLED or not user_id or not (query or "").strip():
        return
    try:
        from app.core.llm import llm_available
        from app.core.llm_invoker import invoke_structured

        old = get_user_preferences(user_id)
        extracted = {"cities": [], "period": ""}
        if llm_available():
            obj, _meta = invoke_structured(
                "从下面的森林火险分析需求中提取用户偏好。州市必须用云南16州市全名"
                "（如：昆明市、玉溪市、大理白族自治州）；没有明确州市/时段就留空。\n"
                f"需求文本：{query[:300]}\n"
                '输出 JSON：{"cities": ["州市全名", ...], "period": "关注时段或空串"}\n'
                "仅输出 JSON。",
                _PrefExtract, temperature=0.0, max_tokens=120)
            if obj is not None:
                extracted = {"cities": [c for c in (obj.cities or []) if c][:5],
                             "period": (obj.period or "").strip()[:20]}
        # 确定性合并：旧城市保持在前（历史权重），新城市追加去重，最多 5 个
        merged_cities = list(old.get("cities") or [])
        for c in extracted["cities"]:
            if c not in merged_cities:
                merged_cities.append(c)
        merged = {
            "cities": merged_cities[:5],
            "period": extracted["period"] or old.get("period", ""),
            "last_query": query[:80],
        }
        store = create_store()
        if store is not None:
            store.put(("prefs", f"user-{user_id}"), "analysis", merged)
    except Exception:
        pass  # 偏好记录失败不影响主流程


def prefs_context(user_id: int) -> str:
    """ReportAgent 注入用的偏好上下文文本（无偏好返回空串）"""
    p = get_user_preferences(user_id)
    if not p:
        return ""
    parts = []
    if p.get("cities"):
        parts.append("- 常查州市：" + "、".join(str(c) for c in p["cities"][:5]))
    if p.get("period"):
        parts.append("- 关注时段：" + str(p["period"]))
    return "\n".join(parts)
