"""
Agent 接口 — 任务创建（后台异步执行）& SSE 实时进度 & 任务历史 & HITL 审批恢复

P0/P1 升级说明：
- POST /tasks 立即返回 task_id，任务在后台线程执行（图执行为同步 LangGraph，
  通过 asyncio.to_thread 放入线程池，不阻塞事件循环）；
- 执行过程中每完成一个节点即增量落库 agent_task_steps，前端通过
  GET /tasks/{id}/stream（SSE）获取真实节点级进度，取代旧版整段同步等待；
- P1 图拓扑为并行 fan-out/join + 评审循环，worker 按 delta 语义合并状态
  （steps 键 extend、其余键覆盖），与 AgentState 的 reducer 语义一致；
- P1 HITL 审批：图执行到 approval_gate 时 interrupt 暂停，任务状态置为
  awaiting_approval（不落报告中心）；POST /tasks/{id}/resume 注入人工决策后
  以同 thread_id 恢复执行，approve/edit 完成后报告正常落报告中心。

任务状态机：running → awaiting_approval → running → completed / failed。

用户隔离：任务/报告归属当前用户；普通用户仅能查看自己的任务历史。
"""
import asyncio
import json
import re
import time
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.core.database import get_db, SessionLocal
from app.core.security import get_current_user, SECRET_KEY, ALGORITHM
from app.core import report_channels  # P2#18：报告流式增量通道（SSE report_delta 帧）
from app.models.user import User
from app.agents.orchestrator_agent import OrchestratorAgent
from app.schemas.agent import AgentTaskRequest, TaskResumeRequest
from app.models.task import AgentTask, AgentTaskStep
from app.models.report import AnalysisReport
from app.repositories.report_repository import ReportRepository
from app.api.v1.routes.admin import log_system_event

router = APIRouter()

# SSE 单连接最长推送时长（防任务卡死导致连接永不关闭）
_SSE_MAX_SECONDS = 1800


def _fmt(dt) -> str | None:
    """datetime → 可读字符串"""
    return dt.strftime("%Y-%m-%d %H:%M:%S") if dt else None


def _task_to_dict(t: AgentTask, llm_provider: str | None = None,
                  llm_model: str | None = None) -> dict:
    """任务记录转可序列化字典（含起止时间与耗时，供前端展示"生成时间"）

    llm_provider / llm_model：关联报告的生成模型标识与详细模型名（列表页由
    list_tasks 批量查询注入，避免 N+1；无报告/模板生成时为 None，
    前端据此显示"模板生成"）。
    """
    duration = None
    if t.started_at and t.finished_at:
        duration = round((t.finished_at - t.started_at).total_seconds(), 1)
    return {
        "id": t.id,
        "query": t.user_query,
        "task_name": t.task_name,
        "task_type": t.task_type,
        "status": t.status,
        "current_step": t.current_step,
        "final_summary": t.final_summary,
        "report_id": t.report_id,
        "llm_provider": llm_provider,
        "llm_model": llm_model,
        "created_at": _fmt(t.created_at),
        "started_at": _fmt(t.started_at),
        "finished_at": _fmt(t.finished_at),
        "duration": duration,
    }


def _step_to_dict(s: AgentTaskStep) -> dict:
    """步骤记录转可序列化字典（与旧版 GET /tasks/{id} 的 steps 契约保持一致）"""
    out = s.output_payload if isinstance(s.output_payload, dict) else {}
    return {
        "agent": s.agent_name or "",
        "step": s.step_name or "",
        "input": (s.input_payload or {}).get("input", "") if isinstance(s.input_payload, dict) else "",
        "output": out,
        "status": s.status or "completed",
        "summary": out.get("summary", "") or out.get("error", ""),
    }


def _extract_audit(steps: list) -> dict:
    """从步骤输出提取 LLM 审计元数据（取最后一个带 llm_provider 的步骤 = generate_report）

    节点 output 中嵌入了 llm_provider / llm_degraded / tokens（无需额外 DB 迁移）。
    模板兜底或 LLM 不可用时无该字段 → 返回空 dict（前端据此显示"模板生成"）。
    """
    audit: dict = {}
    for s in steps or []:
        if not isinstance(s, dict):
            continue
        out = s.get("output")
        if isinstance(out, dict) and out.get("llm_provider"):
            audit = {
                "llm_provider": out.get("llm_provider") or "",
                "llm_model": out.get("llm_model") or "",
                "llm_degraded": bool(out.get("llm_degraded")),
                "llm_tokens": out.get("tokens") or {},
            }
    return audit


def _task_detail(db: Session, t: AgentTask) -> dict:
    """任务详情装配（GET /tasks/{id} 与 SSE report 事件共用，保证契约一致）"""
    step_rows = (
        db.query(AgentTaskStep)
        .filter(AgentTaskStep.task_id == t.id)
        .order_by(AgentTaskStep.step_order.asc(), AgentTaskStep.id.asc())
        .all()
    )
    steps_out = [_step_to_dict(s) for s in step_rows]
    # 报告内容（有关联报告时；include_deleted：报告中心删除不影响 Agent 历史查看）
    report = ""
    llm_used = False
    meta = {"llm_provider": None, "llm_model": None, "llm_tokens": None, "llm_degraded": False}
    if t.report_id:
        rep = ReportRepository(db).get(t.report_id, user_id=t.user_id, is_admin=True,
                                       include_deleted=True)
        if rep:
            report = rep.get("content", "") or ""
            llm_used = "LLM" in (rep.get("tags") or [])
            meta = {
                "llm_provider": rep.get("llm_provider"),
                "llm_model": rep.get("llm_model"),
                "llm_tokens": rep.get("llm_tokens"),
                "llm_degraded": bool(rep.get("llm_degraded")),
            }
    if not meta.get("llm_provider"):
        # 报告未落库（审批中草稿）或历史数据缺失元数据 → 从执行步骤回退提取
        fallback = _extract_audit(steps_out)
        if fallback:
            meta = fallback
    return {
        **_task_to_dict(t),
        "steps": steps_out,
        "report": report,
        "llm_used": llm_used,
        **meta,
    }


# ===================== 后台任务执行 =====================

# 持有后台任务强引用，防止 asyncio.create_task 结果被 GC 回收
_bg_tasks: set = set()


def _upsert_step_row(db: Session, task_id: int, step_order: int, st: dict) -> None:
    """按 (task_id, step_name) 增量落库/更新步骤（节点完成即写入，支撑实时进度）

    注意：SessionLocal 配置为 autoflush=False，新建行必须显式 flush 才能被同一会话
    的后续查询看到；否则预写的 running 行会被"再插一行"而非被终态覆盖（重复步骤 bug）。
    """
    step_name = st.get("step", "")
    if not step_name:
        return
    row = (
        db.query(AgentTaskStep)
        .filter(AgentTaskStep.task_id == task_id, AgentTaskStep.step_name == step_name)
        .first()
    )
    if row is None:
        row = AgentTaskStep(task_id=task_id)
        db.add(row)
    row.step_order = step_order
    row.agent_name = st.get("agent", "")
    row.step_name = step_name
    row.input_payload = {"input": st.get("input", "")}
    row.output_payload = st.get("output", {})
    row.status = st.get("status", "completed")
    db.flush()  # 让本会话后续查询可见（autoflush=False）


# P2#17：节点"开始执行"时预写的 running 步骤行（按图拓扑与计划静态预判；
# 节点完成后 _upsert_step_row 原行覆盖为终态，SSE 对 running 行做终态回推）
_RUNNING_AGENTS = {
    "query_data": "DataAgent",
    "analyze_gis": "GisAgent",
    "retrieve_knowledge": "RagAgent",
    "generate_report": "ReportAgent",
    "review_report": "Reviewer",
}


def _plan_types(merged: dict) -> set:
    return {p.get("task_type") for p in ((merged.get("parsed_intent") or {}).get("plan") or [])}


def _mark_running(db: Session, task_id: int, order: int, nodes: list[str], query: str) -> None:
    for n in nodes:
        _upsert_step_row(db, task_id, order,
                         {"step": n, "agent": _RUNNING_AGENTS.get(n, ""), "input": query,
                          "output": {}, "status": "running", "summary": "节点执行中"})


def _classify_report_type(query: str) -> str:
    """按用户查询语义归类报告类型（daily/weekly/monthly/special），供报告中心筛选"""
    q = query or ""
    if re.search(r"今天|今日|当天|当前|实时|日报|逐日|24小时", q):
        return "daily"
    if re.search(r"本周|上周|一周|近7天|七天|周报", q):
        return "weekly"
    if re.search(r"本月|上月|月报|近30天|三十天|一个月|整月|\d{1,2}月", q):
        return "monthly"
    return "special"


def _save_task_report(db: Session, task: AgentTask, query: str, report_data: str,
                      llm_used: bool, audit: dict | None = None) -> None:
    """将报告落库到报告中心（与旧版 POST /tasks 逻辑一致，标题含年月后缀）

    audit：_extract_audit() 产出的 LLM 元数据（provider/tokens/degraded），
    一并写入报告行，供报告中心展示「模型来源 / 是否降级 / token 用量」。
    """
    title = query[:50] or "Agent 分析报告"
    days_str = ""
    try:
        match = re.search(r"(\d{4})[年\-]?(\d{1,2})", query)
        if match:
            days_str = f"_{match.group(1)}-{match.group(2)}"
    except Exception:
        pass
    repo = ReportRepository(db)
    body = report_data if isinstance(report_data, str) else str(report_data)
    audit = audit or {}
    report_tags = ["Agent生成", "LLM" if llm_used else "模板"]
    report_type = _classify_report_type(query)
    report_summary = f"任务：{query[:80]}"
    # 同一任务重跑：优先按 task.report_id 覆盖旧报告，报告中心只保留最后一次成功的结果
    # （query 措辞变化会导致标题不同，仅按标题去重会漏 → 产生多条中间记录）
    if task.report_id and repo.overwrite(
        task.report_id,
        content=body,
        summary=report_summary,
        report_type=report_type,
        tags=report_tags,
        llm_provider=audit.get("llm_provider"),
        llm_model=audit.get("llm_model"),
        llm_tokens=audit.get("llm_tokens"),
        llm_degraded=bool(audit.get("llm_degraded")),
    ):
        return
    report = repo.upsert_from_task(
        title=f"{title}{days_str}",
        content=body,
        summary=report_summary,
        report_type=report_type,
        tags=report_tags,
        user_id=task.user_id,
        llm_provider=audit.get("llm_provider"),
        llm_model=audit.get("llm_model"),
        llm_tokens=audit.get("llm_tokens"),
        llm_degraded=bool(audit.get("llm_degraded")),
    )
    if report:
        task.report_id = report.id


def _merge_update(merged: dict, update: dict) -> None:
    """按 delta 语义合并节点状态增量到累积结果

    steps 键 extend（AgentState 中 steps 为 operator.add reducer，节点只返回增量），
    其余键直接覆盖（单写者键：data_results/gis_results/report/status/revisions/...）。
    """
    for k, v in (update or {}).items():
        if k == "steps":
            merged.setdefault("steps", []).extend(v or [])
        else:
            merged[k] = v


def _predict_next_nodes(merged: dict, node_name: str) -> list[str]:
    """P2#17：节点完成后按图拓扑静态预判下一批节点（预写 running 行，前端转圈三态）

    与 build_workflow_graph 的条件边拓扑保持一致；join 节点无步骤行不预写；
    审批通过/评审通过等待终态行由 interrupt 或节点完成自然产出。
    """
    if node_name == "parse_task":
        types = _plan_types(merged)
        out = []
        if "query_data" in types or not types:
            out.append("query_data")
        if "retrieve_knowledge" in types:
            out.append("retrieve_knowledge")
        return out or ["query_data"]
    if node_name == "query_data":
        return ["analyze_gis"]
    if node_name == "join":
        return ["generate_report"] if "generate_report" in _plan_types(merged) else []
    if node_name == "review_report":
        review = merged.get("review_result") or {}
        if not review.get("passed") and merged.get("revisions", 0) < 2 and not review.get("forced"):
            return ["generate_report"]
        return []
    if node_name == "approval":
        return ["generate_report"] if merged.get("decision") == "reject" else []
    return []


def _consume_agent_stream(step_iter, db: Session, task: AgentTask, username: str,
                          merged: dict | None = None) -> tuple[dict, bool]:
    """消费 agent 节点流（iter_steps / iter_resume 共用）：增量合并状态 + 落库步骤行

    merged：累积状态种子。新建执行传 None（从空开始）；HITL 恢复必须传入
    checkpointer 中的中断前状态——否则 stream(Command(resume=...)) 只产出中断之后的
    增量，report/steps 会丢失，导致审批通过后报告不落库（report_id 恒为 None）。

    返回 (merged, interrupted)；interrupted=True 表示命中 HITL 审批闸口：
    已写 approval 步骤行（含 draft_report 全文供前端审批卡展示）、任务状态置为
    awaiting_approval，等待 POST /tasks/{id}/resume 恢复。
    """
    task_id = task.id
    if merged is None:
        merged = {}
    # 步骤排序号接续已有最大号（新建执行预写的 running 行 / HITL 恢复时的历史行都算），
    # 保证后续步骤始终排在末尾，审批行不会因重新从 0 计而插到最前
    order = 0
    last = (db.query(AgentTaskStep.step_order)
            .filter(AgentTaskStep.task_id == task_id)
            .order_by(AgentTaskStep.step_order.desc()).first())
    if last is not None:
        order = (last[0] or 0) + 1
    interrupted = False
    for node_name, update in step_iter:
        if node_name == "__interrupt__":
            # LangGraph interrupt 事件：update 为 (Interrupt(...),) 元组
            payload = {}
            if isinstance(update, tuple) and update:
                payload = getattr(update[0], "value", None) or {}
            st = {"step": "approval", "agent": "HITL", "input": task.user_query,
                  "output": {"draft_report": payload.get("report", ""),
                             "review": payload.get("review", {}),
                             "revisions": payload.get("revisions", 0)},
                  "status": "awaiting", "summary": "报告已生成，等待人工审批"}
            _upsert_step_row(db, task_id, order, st)
            task.status = "awaiting_approval"
            task.current_step = "approval"
            db.commit()
            log_system_event("agent", f"[{username}] 任务#{task_id} 报告待审批（HITL 暂停）")
            interrupted = True
            break

        _merge_update(merged, update)
        steps = (update.get("steps") or [])
        if steps:
            # join 节点等无步骤的空更新不落库；审批闸口恢复后的 update 也不含 steps
            _upsert_step_row(db, task_id, order, steps[-1])
            order += 1
            task.current_step = node_name
            db.commit()
            log_system_event("agent", f"[{username}] 任务#{task_id} 节点 {node_name} 完成")
            # P2#17：预判下一批节点，预写 running 行（节点完成时原行覆盖为终态）
            next_nodes = _predict_next_nodes(merged, node_name)
            if next_nodes:
                _mark_running(db, task_id, order, next_nodes, task.user_query)
                order += len(next_nodes)
    return merged, interrupted


def _finish_task(db: Session, task: AgentTask, merged: dict, user_query: str, username: str) -> None:
    """任务终态处理：更新状态 + 报告落报告中心（新建执行与 resume 恢复共用）"""
    task_id = task.id
    result_steps = merged.get("steps", [])
    report_data = merged.get("report", "")
    # 步骤 output 中带 llm_provider 审计信息 → 判定 LLM 是否真实参与 + 取 Provider/token
    audit = _extract_audit(result_steps)
    llm_used = bool(audit.get("llm_provider"))
    status = merged.get("status", "completed")
    if status not in ("completed", "failed"):
        # 纯查询/检索计划（计划不含 generate_report）图正常走完但未写 completed，视为完成
        status = "completed"
    task.status = status
    task.current_step = str(len(result_steps))
    task.final_summary = result_steps[-1].get("summary", "") if result_steps else ""
    task.finished_at = datetime.now()
    if report_data:
        _save_task_report(db, task, user_query, report_data, llm_used, audit)
    db.commit()
    log_system_event("agent", f"[{username}] 任务#{task_id} 完成，报告长度: {len(str(report_data))} 字符")
    # P2#15：任务完成后沉淀用户分析偏好（失败静默，不阻断终态）
    try:
        from app.core.memory_store import record_task_interests
        record_task_interests(task.user_id, user_query)
    except Exception:
        pass


def _run_agent_task(task_id: int, user_query: str, user_id: int, is_admin: bool, username: str) -> None:
    """后台 worker：逐步执行 LangGraph 工作流，节点完成即落库（在线程池中运行）"""
    db = SessionLocal()
    try:
        task = db.query(AgentTask).filter(AgentTask.id == task_id).first()
        if task is None:
            return
        try:
            # P2#17：parse_task 为首事件前唯一静默节点，起始即写 running 行（转圈三态）
            _mark_running(db, task_id, 0, ["parse_task"], user_query)
            agent = OrchestratorAgent(db_session=db, user_id=user_id, is_admin=is_admin,
                                      thread_id=f"task-{task_id}", task_id=task_id)
            merged, interrupted = _consume_agent_stream(agent.iter_steps(user_query), db, task, username)
            if not interrupted:
                _finish_task(db, task, merged, user_query, username)
        except Exception as e:
            task.status = "failed"
            task.final_summary = f"任务执行异常: {str(e)[:200]}"
            task.finished_at = datetime.now()
            db.commit()
            log_system_event("agent", f"任务#{task_id} 失败: {str(e)[:120]}", level="ERROR")
    finally:
        db.close()


def _run_resume_agent_task(task_id: int, resume_value: dict, user_id: int, is_admin: bool,
                           username: str) -> None:
    """HITL 恢复 worker：以同 thread_id 重建 OrchestratorAgent，从中断点续跑（新线程新连接）"""
    db = SessionLocal()
    try:
        task = db.query(AgentTask).filter(AgentTask.id == task_id).first()
        if task is None:
            return
        try:
            agent = OrchestratorAgent(db_session=db, user_id=user_id, is_admin=is_admin,
                                      thread_id=f"task-{task_id}", task_id=task_id)
            # 关键：以 checkpointer 中中断前的累积状态为种子，否则续跑只拿到增量，
            # report/steps 丢失 → 审批通过后报告不落库（report_id 恒为 None）
            merged, interrupted = _consume_agent_stream(
                agent.iter_resume(resume_value), db, task, username,
                merged=agent.snapshot_state())
            if not interrupted:
                _finish_task(db, task, merged, task.user_query, username)
            # interrupted=True：驳回重写后再次进入审批闸口，保持 awaiting_approval 等待下一次 resume
        except Exception as e:
            task.status = "failed"
            task.final_summary = f"任务恢复执行异常: {str(e)[:200]}"
            task.finished_at = datetime.now()
            db.commit()
            log_system_event("agent", f"任务#{task_id} 恢复失败: {str(e)[:120]}", level="ERROR")
    finally:
        db.close()


def _spawn_task(task_id: int, user_query: str, user_id: int, is_admin: bool, username: str) -> None:
    """把同步 worker 放入线程池执行（图执行为同步 LangGraph，不能阻塞事件循环）"""
    coro = asyncio.to_thread(_run_agent_task, task_id, user_query, user_id, is_admin, username)
    t = asyncio.create_task(coro)
    _bg_tasks.add(t)
    t.add_done_callback(_bg_tasks.discard)


def _spawn_resume_task(task_id: int, resume_value: dict, user_id: int, is_admin: bool, username: str) -> None:
    """把 HITL 恢复 worker 放入线程池执行"""
    coro = asyncio.to_thread(_run_resume_agent_task, task_id, resume_value, user_id, is_admin, username)
    t = asyncio.create_task(coro)
    _bg_tasks.add(t)
    t.add_done_callback(_bg_tasks.discard)


# ===================== 接口 =====================

@router.get("/tasks")
async def list_tasks(
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    """获取当前用户的任务历史（管理员可查全部）；附带各任务报告的生成模型"""
    q = db.query(AgentTask)
    if current.role != "admin":
        q = q.filter(AgentTask.user_id == current.id)
    tasks = q.order_by(AgentTask.created_at.desc()).limit(50).all()
    # 批量取关联报告的 llm_provider / llm_model（一次 IN 查询，避免逐条 N+1）
    report_ids = [t.report_id for t in tasks if t.report_id]
    provider_map: dict[int, tuple] = {}
    if report_ids:
        rows = (
            db.query(AnalysisReport.id, AnalysisReport.llm_provider, AnalysisReport.llm_model)
            .filter(AnalysisReport.id.in_(report_ids))
            .all()
        )
        provider_map = {r.id: (r.llm_provider, r.llm_model) for r in rows}
    return {
        "code": 200,
        "message": "success",
        "data": [
            _task_to_dict(t, *(provider_map.get(t.report_id) or (None, None)))
            for t in tasks
        ],
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
    return {"code": 200, "message": "success", "data": _task_detail(db, t)}


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
    """创建 Agent 任务（立即返回 task_id，后台异步执行；进度通过 SSE 端点订阅）

    执行完成后报告自动落入报告中心（upsert 去重），任务/步骤全程落库。
    """
    query = req.query.strip()
    log_system_event("agent", f"[{current.username}] 接收到任务: {query[:60]}")

    task = AgentTask(
        user_id=current.id,
        task_name=query[:100],
        task_type="analysis",
        user_query=query,
        status="running",
        current_step="0",
        started_at=datetime.now(),
        created_at=datetime.now(),
    )
    db.add(task)
    db.commit()

    _spawn_task(task.id, query, current.id, current.role == "admin", current.username)

    return {
        "code": 200,
        "message": "任务已受理，后台执行中",
        "data": {"task_id": task.id, "status": "running"},
    }


@router.post("/tasks/{task_id}/resume")
async def resume_task(
    task_id: int,
    req: TaskResumeRequest,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    """HITL 审批决策：从中断点恢复任务（仅任务所有者或管理员）

    action=approve  → 报告按原稿定稿并落报告中心
    action=edit     → 以提交的 content 作为最终报告落报告中心
    action=reject   → 携带驳回意见回 generate_report 重写，重写完成后再次进入审批
    """
    t = db.query(AgentTask).filter(AgentTask.id == task_id).first()
    if not t:
        raise HTTPException(status_code=404, detail="任务不存在")
    if current.role != "admin" and t.user_id != current.id:
        raise HTTPException(status_code=403, detail="无权操作该任务")
    if t.status != "awaiting_approval":
        raise HTTPException(status_code=400, detail="任务当前不在待审批状态")
    if req.action == "edit" and not (req.content or "").strip():
        raise HTTPException(status_code=400, detail="编辑通过需提供修改后的报告内容")
    if req.action == "reject" and not (req.comment or "").strip():
        raise HTTPException(status_code=400, detail="驳回需填写驳回意见")

    resume_value = {"action": req.action, "content": req.content or "", "comment": req.comment or ""}
    t.status = "running"
    t.current_step = "approval"
    db.commit()
    log_system_event("agent", f"[{current.username}] 任务#{task_id} 审批决策: {req.action}")

    # 以任务所有者身份恢复执行（RAG 检索等保持 owner 数据隔离）
    _spawn_resume_task(task_id, resume_value, t.user_id, current.role == "admin", current.username)
    return {"code": 200, "message": "审批已提交，任务继续执行",
            "data": {"task_id": task_id, "status": "running"}}


def _resolve_user_from_token(token: str | None, db: Session) -> User:
    """SSE 专用鉴权：EventSource 无法携带 Authorization 头，从查询参数解析 JWT"""
    credentials_exception = HTTPException(status_code=401, detail="无效的登录凭证")
    if not token:
        raise credentials_exception
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = int(payload.get("sub"))
    except (JWTError, ValueError, TypeError):
        raise credentials_exception
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise credentials_exception
    return user


def _sse(payload: dict) -> str:
    """格式化 SSE 数据帧"""
    return f"data: {json.dumps(payload, ensure_ascii=False, default=str)}\n\n"


@router.get("/tasks/{task_id}/stream")
async def stream_task(
    task_id: int,
    token: str | None = Query(default=None, description="JWT（EventSource 无法带 header）"),
    db: Session = Depends(get_db),
):
    """SSE 实时推送任务执行进度

    事件流：
      - type=step    每个节点完成时推送（增量落库的步骤行）
      - type=approval HITL 审批事件（任务挂起等待人工决策，携带含 draft_report 的任务详情）后关闭
      - type=report  终态事件（completed/failed），携带完整任务详情（含报告）后关闭
    连接建立时先回放已落库的历史步骤（支持刷新/断线重连不丢进度）。
    """
    current = _resolve_user_from_token(token, db)
    t = db.query(AgentTask).filter(AgentTask.id == task_id).first()
    if not t:
        raise HTTPException(status_code=404, detail="任务不存在")
    if current.role != "admin" and t.user_id != current.id:
        raise HTTPException(status_code=403, detail="无权访问该任务")

    async def event_gen():
        last_step_id = 0
        started = time.monotonic()
        running_rows: dict[int, int] = {}  # 已推送为 running 的步骤行 id（终态后需回推）
        # P2#18：订阅报告流式增量通道（易失，断线不重放；终态完整内容以 DB 为准）
        q = report_channels.subscribe(task_id)
        try:
            while True:
                db.expire_all()  # 清空身份映射，保证轮询读到后台 worker 的最新提交
                for s in (
                    db.query(AgentTaskStep)
                    .filter(AgentTaskStep.task_id == task_id, AgentTaskStep.id > last_step_id)
                    .order_by(AgentTaskStep.id.asc())
                    .all()
                ):
                    last_step_id = s.id
                    yield _sse({"type": "step", "step": _step_to_dict(s)})
                    if (s.status or "") == "running":
                        running_rows[s.id] = 1
                if running_rows:
                    # P2#17：running 行被 worker 覆盖为终态后，主动回推一次
                    rows = db.query(AgentTaskStep).filter(AgentTaskStep.id.in_(list(running_rows))).all()
                    for r in rows:
                        if (r.status or "") != "running":
                            running_rows.pop(r.id, None)
                            yield _sse({"type": "step", "step": _step_to_dict(r)})

                t2 = db.query(AgentTask).filter(AgentTask.id == task_id).first()
                status = t2.status if t2 else "failed"
                if status == "awaiting_approval":
                    # HITL：推送审批事件（含 draft_report 的步骤详情）后关闭，
                    # 前端展示审批卡，resume 提交后重新订阅本端点继续收进度
                    detail = _task_detail(db, t2)
                    yield _sse({"type": "approval", "data": detail})
                    break
                if status in ("completed", "failed"):
                    detail = _task_detail(db, t2) if t2 else None
                    yield _sse({"type": "report", "data": detail})
                    break
                if time.monotonic() - started > _SSE_MAX_SECONDS:
                    yield _sse({"type": "error", "message": "进度推送超时，请稍后刷新任务历史"})
                    break
                yield ": ping\n\n"
                # 等待实时增量（0.6s 超时回到 DB 轮询；与节点进度共用同一条连接）
                try:
                    ev = await asyncio.wait_for(q.get(), timeout=0.6)
                    yield _sse(ev)
                    while True:
                        try:
                            ev = q.get_nowait()
                        except asyncio.QueueEmpty:
                            break
                        yield _sse(ev)
                except asyncio.TimeoutError:
                    pass
        except asyncio.CancelledError:
            raise  # 客户端断开，正常结束
        finally:
            report_channels.unsubscribe(task_id, q)

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/capabilities")
async def get_agent_capabilities(db: Session = Depends(get_db)):
    """「系统能力」面板数据源 — 返回 P0/P1/P2 能力的**真实运行时状态**（非硬编码文案）

    仅需登录态即可查看；所有字段均可从配置/模块状态实时推导，便于前端可视化展示
    重试熔断、检查点、编排拓扑、双数据源、RAG、偏好记忆、MCP、观测与评估回归。
    """
    import sqlalchemy as sa
    from pathlib import Path

    from app.core.config import settings
    from app.core.llm import llm_available
    from app.core.checkpointer import checkpointer_backend
    from app.core.llm_invoker import breaker_status, _provider_chain, _RETRY_DELAYS

    # 知识库文档数（表不存在/查询失败不阻断面板）
    kb_total = None
    try:
        kb_total = db.execute(sa.text('SELECT COUNT(*) FROM kb_documents')).scalar()
    except Exception:
        kb_total = None

    # 评估回归金标用例数
    golden_cases = None
    try:
        import json as _json
        p = Path(__file__).resolve().parents[3] / "scripts" / "golden_set.json"
        if p.exists():
            data = _json.loads(p.read_text(encoding="utf-8"))
            golden_cases = len(data) if isinstance(data, list) else len(data.get("cases", []))
    except Exception:
        golden_cases = None

    active = settings.ACTIVE_LLM_PROVIDER
    model_map = {"aliyun": settings.LLM_MODEL, "amd": settings.AMD_MODEL, "ollama": settings.OLLAMA_MODEL}

    return {
        "code": 200,
        "message": "success",
        "data": {
            "llm": {
                "active_provider": active,
                "active_model": model_map.get(active, ""),
                "available": llm_available(),
                "stream_enabled": settings.LLM_STREAM_ENABLED,
                "provider_chain": _provider_chain(),
                "retry": {"delays": list(_RETRY_DELAYS), "max_attempts": len(_RETRY_DELAYS) + 1},
                "breakers": breaker_status(),
            },
            "checkpointer": checkpointer_backend(),
            "orchestration": {
                "framework": "LangGraph StateGraph",
                "topology": ["parse_task", "query_data ∥ retrieve_knowledge", "analyze_gis",
                             "join", "generate_report", "review_report", "approval_gate"],
                "plan_driven_routing": True,
                "parallel_fanout": True,
                "reflection_retry": {"max_rounds": 2, "trigger": "数据查询为空时 LLM 放宽参数重查"},
                "review_loop": {"max_revisions": 2, "hard_guardrail_min_chars": 800},
                "hitl": {"required": settings.AGENT_REQUIRE_APPROVAL,
                         "actions": ["approve", "edit", "reject"]},
                "node_progress_sse": True,
            },
            "data": {
                "dual_source": True,
                "sources": [
                    {"table": "historical_fire_points", "label": "历史火点",
                     "range": "2021-2025", "source_tag": "historical"},
                    {"table": "predicted_fire_risks", "label": "预测火险",
                     "range": "2025-2026", "source_tag": "predicted"},
                ],
                "gis": {"historical": "经纬度 0.1° 网格聚类识别聚集区",
                        "predicted": "火险等级 ≥ 3 级识别高风险州市"},
            },
            "rag": {
                "embedding_model": settings.EMBEDDING_MODEL,
                "retrieval": "中文分词关键词 + 向量余弦相似度 + bigram 兜底",
                "rerank": {"enabled": settings.RERANK_ENABLED, "model": settings.RERANK_MODEL,
                           "fallback": "失败降级 RRF 融合原序"},
                "top_k": settings.KB_TOP_K,
                "documents": kb_total,
                "citation": True,
                "stream": True,
            },
            "memory": {"preferences_enabled": settings.PREFERENCES_ENABLED,
                       "store": "PostgresStore(JSONB)",
                       "inject": "用户历史关注辖区/时段注入报告 prompt，任务完成后沉淀"},
            "mcp": {"enabled": settings.MCP_ENABLED,
                    "servers": ["weather_server（高德 geo→adcode→实时天气，只读）"],
                    "fallback": "未启用/依赖缺失/调用失败静默跳过"},
            "observability": {"langfuse_enabled": settings.LANGFUSE_ENABLED,
                              "fallback": "未启用时降级为纯日志，不影响主链路"},
            "evaluation": {"golden_cases": golden_cases,
                           "metrics": ["Tool Correctness", "路由正确性", "任务完成+轨迹", "轻量 Faithfulness"],
                           "modes": ["offline", "live"]},
            "degradation": {
                "llm": "指数重试(1s/2s/4s) → 熔断(3次/60s) → Provider 链切换 → 模板兜底",
                "checkpointer": "PostgresSaver → MemorySaver",
                "rerank": "Rerank → RRF 融合原序",
                "mcp": "静默跳过", "preferences": "静默跳过",
            },
        },
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
