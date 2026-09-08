"""
Agent 接口 — 任务执行 & 状态查询 & 任务历史

用户隔离：任务/报告归属当前用户；普通用户仅能查看自己的任务历史。
"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.agents.orchestrator_agent import OrchestratorAgent
from app.schemas.agent import AgentTaskRequest
from app.models.task import AgentTask, AgentTaskStep
from app.repositories.report_repository import ReportRepository
from app.api.v1.routes.admin import log_system_event

router = APIRouter()


def _task_to_dict(t: AgentTask) -> dict:
    """任务记录转可序列化字典"""
    return {
        "id": t.id,
        "query": t.user_query,
        "task_name": t.task_name,
        "task_type": t.task_type,
        "status": t.status,
        "current_step": t.current_step,
        "final_summary": t.final_summary,
        "report_id": t.report_id,
        "created_at": t.created_at.strftime("%Y-%m-%d %H:%M:%S") if t.created_at else None,
    }


@router.get("/tasks")
async def list_tasks(
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    """获取当前用户的任务历史（管理员可查全部）"""
    q = db.query(AgentTask)
    if current.role != "admin":
        q = q.filter(AgentTask.user_id == current.id)
    tasks = q.order_by(AgentTask.created_at.desc()).limit(50).all()
    return {
        "code": 200,
        "message": "success",
        "data": [_task_to_dict(t) for t in tasks],
    }


@router.get("/tasks/{task_id}")
async def get_task(
    task_id: int,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    """任务详情：含执行步骤（Agent 执行过程）与报告内容（用户数据隔离）"""
    t = db.query(AgentTask).filter(AgentTask.id == task_id).first()
    if not t:
        raise HTTPException(status_code=404, detail="任务不存在")
    if current.role != "admin" and t.user_id != current.id:
        raise HTTPException(status_code=403, detail="无权访问该任务")

    step_rows = (
        db.query(AgentTaskStep)
        .filter(AgentTaskStep.task_id == task_id)
        .order_by(AgentTaskStep.step_order.asc())
        .all()
    )
    steps = []
    for s in step_rows:
        out = s.output_payload if isinstance(s.output_payload, dict) else {}
        steps.append({
            "agent": s.agent_name or "",
            "step": s.step_name or "",
            "input": (s.input_payload or {}).get("input", "") if isinstance(s.input_payload, dict) else "",
            "output": out,
            "status": s.status or "completed",
            "summary": out.get("summary", "") or out.get("error", ""),
        })

    # 报告内容（有关联报告时；include_deleted：报告中心删除不影响 Agent 历史查看）
    report = ""
    llm_used = False
    if t.report_id:
        rep = ReportRepository(db).get(t.report_id, user_id=t.user_id, is_admin=True,
                                       include_deleted=True)
        if rep:
            report = rep.get("content", "") or ""
            llm_used = "LLM" in (rep.get("tags") or [])

    return {
        "code": 200,
        "message": "success",
        "data": {**_task_to_dict(t), "steps": steps, "report": report, "llm_used": llm_used},
    }


@router.delete("/tasks/{task_id}")
async def delete_task(
    task_id: int,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    """删除任务历史（仅本人或管理员）"""
    t = db.query(AgentTask).filter(AgentTask.id == task_id).first()
    if not t or (current.role != "admin" and t.user_id != current.id):
        raise HTTPException(status_code=404, detail="任务不存在或无权限删除")
    db.query(AgentTaskStep).filter(AgentTaskStep.task_id == task_id).delete()
    db.delete(t)
    db.commit()
    return {"code": 200, "message": "success", "data": {"id": task_id}}


@router.post("/tasks")
async def create_task(
    req: AgentTaskRequest,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    """创建 Agent 任务并执行，生成的报告自动落入报告中心，任务/步骤落库（归属当前用户）"""
    agent = OrchestratorAgent(db_session=db, user_id=current.id, is_admin=current.role == "admin")
    log_system_event("agent", f"[{current.username}] 接收到任务: {req.query.strip()[:60]}")

    # 创建任务记录（落库）
    task = AgentTask(
        user_id=current.id,
        task_name=req.query.strip()[:100],
        task_type="analysis",
        user_query=req.query.strip(),
        status="running",
        current_step=0,
        started_at=datetime.now(),
    )
    db.add(task)
    db.flush()

    try:
        result = await agent.execute(req.query)
        report_data = result.get("report", "")

        # 任务步骤落库
        for i, st in enumerate(result.get("steps", [])):
            db.add(AgentTaskStep(
                task_id=task.id,
                step_order=i,
                agent_name=st.get("agent", ""),
                step_name=st.get("step", ""),
                input_payload={"input": st.get("input", "")},
                output_payload=st.get("output", {}),
                status=st.get("status", "completed"),
            ))

        task.status = result.get("status", "failed")
        task.current_step = str(len(result.get("steps", [])))
        task.final_summary = (result.get("steps") or [{}])[-1].get("summary", "") if result.get("steps") else ""
        task.finished_at = datetime.now()
        log_system_event("agent", f"任务完成，报告长度: {len(str(report_data))} 字符")

        # 将报告落库（标题取自用户查询，归属当前用户）
        title = req.query.strip()[:50] or "Agent 分析报告"
        if report_data:
            summary = f"任务：{req.query.strip()[:80]}"
            days_str = ""
            try:
                import re
                match = re.search(r"(\d{4})[年\-]?(\d{1,2})", req.query)
                if match:
                    days_str = f"_{match.group(1)}-{match.group(2)}"
            except Exception:
                pass
            repo = ReportRepository(db)
            body = report_data if isinstance(report_data, str) else str(report_data)
            report = repo.upsert_from_task(
                title=f"{title}{days_str}",
                content=body,
                summary=summary,
                report_type="special",
                tags=["Agent生成", "LLM" if result.get("llm_used") else "模板"],
                user_id=current.id,
            )
            if report:
                task.report_id = report.id
        db.commit()
    except Exception as e:
        task.status = "failed"
        task.final_summary = f"任务执行异常: {str(e)[:200]}"
        task.finished_at = datetime.now()
        db.commit()
        log_system_event("agent", f"任务失败: {str(e)[:120]}", level="ERROR")
        raise

    return {
        "code": 200,
        "message": "success",
        "data": {**result, "task_id": task.id, "report_id": task.report_id},
    }


@router.get("/status")
async def get_agent_status():
    """获取 Agent 系统状态"""
    return {
        "code": 200,
        "message": "success",
        "data": {
            "status": "running",
            "agents": [
                {"name": "Orchestrator", "framework": "LangGraph", "status": "ready"},
                {"name": "DataAgent", "framework": "LangChain Tool", "status": "ready"},
                {"name": "GisAgent", "framework": "Turf/Shapely", "status": "ready"},
                {"name": "ReportAgent", "framework": "LangChain LLM", "status": "ready"},
                {"name": "RagAgent", "framework": "LangChain RAG", "status": "ready"},
            ],
        },
    }
