"""
LangGraph Checkpointer 工厂 — PostgresSaver 优先，环境不具备时降级 MemorySaver

- PostgresSaver：任务状态持久化到 PostgreSQL（与业务库同实例），服务重启后
  任务线程（thread_id）状态可恢复，是后续 HITL / 断点续跑的基础。
- MemorySaver：未安装 psycopg3 / langgraph-checkpoint-postgres 或连不上库时
  自动降级（进程内保存，重启丢失）——保证系统"降级不瘫痪"。

注意：每个任务线程使用独立连接（psycopg 连接非线程安全，禁止跨线程共享）。
"""
import threading

from app.core.config import settings

# 模块级状态：setup 全局只执行一次（PostgresSaver.setup 为幂等 DDL）
_setup_lock = threading.Lock()
_setup_done = False
_postgres_disabled = False  # 一旦探测失败，后续直接走 MemorySaver，避免每次任务都重试连接


def _conninfo() -> str:
    """把 SQLAlchemy DATABASE_URL 归一化为 psycopg3 连接串

    postgresql+psycopg2://user:pass@host:5432/db → postgresql://user:pass@host:5432/db
    """
    url = settings.DATABASE_URL
    if "://" in url:
        scheme, rest = url.split("://", 1)
        if "+" in scheme:
            url = f"postgresql://{rest}"
    return url


def create_checkpointer():
    """创建新的 checkpointer 实例（每个任务执行方调用一次，独享连接保证线程安全）"""
    global _setup_done, _postgres_disabled
    if not _postgres_disabled:
        conn = None
        try:
            import psycopg
            from langgraph.checkpoint.postgres import PostgresSaver

            conn = psycopg.connect(_conninfo(), autocommit=True)
            saver = PostgresSaver(conn)
            with _setup_lock:
                if not _setup_done:
                    saver.setup()
                    _setup_done = True
            return saver
        except Exception:
            # Postgres 不可用 → 本次连接丢弃，全局标记降级
            _postgres_disabled = True
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass

    from langgraph.checkpoint.memory import MemorySaver
    return MemorySaver()


def checkpointer_backend() -> dict:
    """当前 checkpointer 后端状态（供「系统能力」面板展示真实运行态）"""
    if _postgres_disabled:
        return {
            "backend": "memory",
            "persistent": False,
            "note": "psycopg3 / langgraph-checkpoint-postgres 不可用，已自动降级为进程内 MemorySaver",
        }
    return {
        "backend": "postgres",
        "persistent": True,
        "note": "LangGraph 状态按 thread_id 持久化至 PostgreSQL，服务重启后可恢复（HITL 审批续跑基础）",
    }
