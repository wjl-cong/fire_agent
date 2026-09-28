"""
FastAPI 应用入口
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.database import engine, Base
from app.api.v1.routes import dashboard as dashboard_router
from app.api.v1.routes import query as query_router
from app.api.v1.routes import rag as rag_router
from app.api.v1.routes import agent as agent_router
from app.api.v1.routes import report as report_router
from app.api.v1.routes import admin as admin_router
from app.api.v1.routes import auth as auth_router
from app.api.v1.routes import media as media_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动时建表 + 兼容旧库补列 + 种子管理员账号"""
    # 启动时创建所有表（开发阶段方便，生产环境用 Alembic）
    Base.metadata.create_all(bind=engine)

    # 兼容旧库：create_all 不会修改已存在的表，这里幂等地补充新增列（如 user_id）
    from app.core.database import SessionLocal
    import sqlalchemy as sa
    db = SessionLocal()
    try:
        for table, col, coltype in (
            ("kb_documents", "user_id", "INTEGER"),
            ("analysis_reports", "user_id", "INTEGER"),
            ("analysis_reports", "llm_provider", "VARCHAR(50)"),
            ("analysis_reports", "llm_model", "VARCHAR(120)"),
            ("analysis_reports", "llm_tokens", "JSON"),
            ("analysis_reports", "llm_degraded", "BOOLEAN DEFAULT FALSE"),
            ("agent_tasks", "user_id", "INTEGER"),
            ("query_history", "result", "JSON"),
            ("rag_history", "result", "JSON"),
        ):
            try:
                db.execute(sa.text(
                    f'ALTER TABLE "{table}" ADD COLUMN IF NOT EXISTS "{col}" {coltype}'
                ))
            except Exception as e:
                print(f"[INIT] 为 {table}.{col} 补列失败（可能表不存在）: {e}")
        db.commit()
    finally:
        db.close()

    # 种子默认管理员（admin/123456），已存在则跳过
    from app.core.security import hash_password
    from app.models.user import User
    db = SessionLocal()
    try:
        if not db.query(User).filter(User.username == "admin").first():
            db.add(User(
                username="admin",
                email=None,
                password_hash=hash_password("123456"),
                role="admin",
            ))
            db.commit()
            print("[INIT] 已创建默认管理员账号: admin / 123456")
    finally:
        db.close()

    # 启动自愈：worker 随进程消亡，running 任务不可能再推进 → 标记中断；
    # awaiting_approval 不动（HITL 中断态存于 PostgresSaver，重启后仍可审批恢复）
    from datetime import datetime
    from app.models.task import AgentTask, AgentTaskStep
    db = SessionLocal()
    try:
        stuck = db.query(AgentTask).filter(AgentTask.status == "running").all()
        for t in stuck:
            t.status = "failed"
            t.final_summary = "服务重启导致任务中断，请重新发起任务"
            t.finished_at = datetime.now()
        if stuck:
            db.commit()
            print(f"[INIT] 已将 {len(stuck)} 个中断的 running 任务标记为 failed")

        # 清理僵尸 running 步骤行：① 同 (task_id, step_name) 已被终态行取代的历史重复行
        # ② 归属于已中断任务、永远不会再推进的 running 行
        running_rows = db.query(AgentTaskStep).filter(AgentTaskStep.status == "running").all()
        terminal_keys = {(r.task_id, r.step_name) for r in db.query(AgentTaskStep).all()
                         if (r.status or "") != "running"}
        dead_ids = {t.id for t in stuck}
        removed = 0
        for r in running_rows:
            if (r.task_id, r.step_name) in terminal_keys or r.task_id in dead_ids:
                db.delete(r)
                removed += 1
        if removed:
            db.commit()
            print(f"[INIT] 已清理 {removed} 条僵尸 running 步骤行")
    finally:
        db.close()

    yield


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="焰哨多Agent与可视化平台 · 后端服务",
    lifespan=lifespan,
)

# CORS — 允许前端跨域访问
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ===== 注册路由 =====
app.include_router(dashboard_router.router, prefix="/api/v1/dashboard", tags=["大屏数据"])
app.include_router(query_router.router, prefix="/api/v1/query", tags=["智能查询"])
app.include_router(rag_router.router, prefix="/api/v1/rag", tags=["知识库 RAG"])
app.include_router(agent_router.router, prefix="/api/v1/agent", tags=["Agent 协作"])
app.include_router(report_router.router, prefix="/api/v1/reports", tags=["报告中心"])
app.include_router(admin_router.router, prefix="/api/v1/admin", tags=["系统管理"])
app.include_router(auth_router.router, prefix="/api/v1/auth", tags=["认证"])
app.include_router(media_router.router, prefix="/api/v1/vision", tags=["视觉与语音"])


@app.get("/")
async def root():
    return {
        "service": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "status": "running",
    }


@app.get("/health")
async def health():
    return {"status": "ok"}