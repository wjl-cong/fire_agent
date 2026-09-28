"""
编排 Agent — 使用 LangGraph StateGraph 做任务编排（P1 升级版）

P1 新增能力：
- #5 plan 驱动路由：parse_task 结构化产出执行计划，后续节点按计划执行/跳过（跳过=no-op 节点，保留 join 屏障正确性）
- #6 并行 fan-out/join：query_data 与 retrieve_knowledge 并行执行，join 节点汇聚
- #7 反思重试：query_data 结果为空时由 LLM 反思放宽参数重查（最多 2 轮）
- #8 评审循环：review_report 低温度 LLM 评审 + 硬护栏，不通过带意见回 generate_report 重写（最多 2 轮）
- #11 HITL 审批：approval_gate 使用 langgraph interrupt 暂停，resume 端点注入人工决策

并发防冲突约定（重要）：
- steps / knowledge_results 使用 operator.add reducer，所有节点只返回 delta（新增的部分），禁止返回全量列表；
- status 键仅由 parse_task（"parsed"）与 generate_report / approval_gate（"completed"）写入，
  并行波次节点不得写 status，条件路由一律读取 parsed_intent.plan，不读 status。
"""
import json
import operator
from typing import TYPE_CHECKING, Annotated, Any, TypedDict, Literal, Callable

from pydantic import BaseModel, Field

from app.core.config import settings
from app.core.checkpointer import create_checkpointer
from app.core.llm import llm_available
from app.core.llm_invoker import invoke_llm, invoke_structured, stream_llm, LLMResult

# 仅用于类型检查解析，避免运行时强制导入 langgraph（保持懒加载、加快启动）
if TYPE_CHECKING:
    from langgraph.graph import CompiledStateGraph


# ===== 任务计划结构化输出 Schema（parse_task 使用，驱动 P1 条件路由） =====
class SubTaskPlan(BaseModel):
    """单个子任务"""
    task_type: Literal["query_data", "analyze_gis", "retrieve_knowledge", "generate_report"] = Field(
        description="子任务类型")
    description: str = Field(default="", description="子任务具体描述")
    reason: str = Field(default="", description="为什么需要/不需要该子任务")
    required: bool = Field(default=True, description="该子任务是否必须执行")


class TaskPlan(BaseModel):
    """Orchestrator 拆解出的执行计划"""
    plan: list[SubTaskPlan] = Field(default_factory=list, description="子任务列表")


# ===== 反思重试 Schema（query_data 为空时 LLM 调整查询参数） =====
class QueryRetryPlan(BaseModel):
    """查询为空时的参数调整建议（None 字段 = 放宽为不限）"""
    reason: str = Field(default="", description="查询为空的可能原因")
    adjusted_year: int | None = Field(default=None, description="调整后的年份；null 表示不限年份")
    adjusted_month: int | None = Field(default=None, description="调整后的月份(1-12)；null 表示不限月份")
    adjusted_city: str | None = Field(default=None, description="调整后的州市名；null 表示不限州市")
    adjusted_view_mode: Literal["daily", "monthly"] | None = Field(
        default=None, description="调整后的视图模式；null 表示不限")


# ===== 报告评审 Schema（review_report 使用） =====
class ReviewVerdict(BaseModel):
    """报告评审结论"""
    passed: bool = Field(description="报告是否通过评审")
    issues: list[str] = Field(default_factory=list, description="发现的问题列表")
    suggestion: str = Field(default="", description="针对性修改建议")


def _parse_plan_text(text: str) -> TaskPlan | None:
    """结构化输出失败时的文本解析兜底（兼容旧版 ```json 清洗逻辑）"""
    try:
        text = text.strip().removeprefix("```json").removesuffix("```").strip()
        data = json.loads(text)
        if not isinstance(data, list):
            data = data.get("plan") if isinstance(data, dict) else None
        if not isinstance(data, list):
            return None
        allowed = {"query_data", "analyze_gis", "retrieve_knowledge", "generate_report"}
        plan = [SubTaskPlan(task_type=d.get("task_type"), description=d.get("description", ""),
                            reason=d.get("reason", ""), required=bool(d.get("required", True)))
                for d in data if isinstance(d, dict) and d.get("task_type") in allowed]
        return TaskPlan(plan=plan)
    except Exception:
        return None


# ===== LangGraph 状态定义（并发安全：steps / knowledge_results 用 add reducer，节点只返回 delta） =====
class AgentState(TypedDict):
    """Agent 工作流状态"""
    user_query: str
    parsed_intent: dict
    data_results: dict
    gis_results: dict
    knowledge_results: Annotated[list, operator.add]
    report: str
    status: str
    steps: Annotated[list[dict], operator.add]
    error: str | None
    # P1：评审循环 + HITL 审批
    revisions: int            # 报告重写轮次（评审驳回计数）
    review_result: dict       # 最新评审结论 {passed, issues, suggestion, forced?}
    decision: str             # 审批决策 approve / edit / reject
    rejection_feedback: str   # 用户驳回意见（reject 时注入报告重写 prompt）


def _stream_report(prompt: str, task_id: int):
    """P2#18：流式生成报告（增量经 report_channels 实时推送 SSE）

    返回 LLMResult（流式成功）或 None（流式失败，调用方走非流式兜底）。
    通道易失：无订阅者时 push 为 no-op，worker 不受影响；半截内容不落库，
    终态完整报告仍由节点返回值落库（DB 唯一事实源）。
    """
    from app.core import report_channels
    run = report_channels.begin_generation(task_id)  # 重写轮次递增，前端据此清缓冲
    buf: list[str] = []
    result = None
    try:
        for chunk in stream_llm(prompt, temperature=0.4, max_tokens=4000, enable_thinking=False):
            ctype = chunk.get("type")
            if ctype == "delta":
                buf.append(chunk.get("text", ""))
                report_channels.push_delta(task_id, run, chunk.get("text", ""))
            elif ctype == "meta":
                # 全程 0 字符的"成功"（如思考型模型 token 全花在 reasoning、content 为空）
                # 视为失败：result 置 None，让调用方走非流式/模板兜底，避免落库空报告
                if buf:
                    result = LLMResult(text="".join(buf), provider=chunk.get("provider", ""),
                                       tokens=chunk.get("tokens") or {},
                                       degraded=bool(chunk.get("degraded")),
                                       model=chunk.get("model", ""))
                break
            elif ctype == "error":
                break
    except Exception:
        result = None
    return result


# ===== 节点工厂（注入 db session 依赖） =====

def _make_nodes(db_session, user_id=None, is_admin=False, task_id=None):
    """构造依赖 db 的节点函数（闭包），使 LangGraph 节点能访问数据库"""
    from app.repositories.fire_repository import FireRepository
    from app.agents.gis_agent import GisAgent
    from app.services.rag_service import RagService

    fire_repo = FireRepository(db_session)
    gis_agent = GisAgent()
    rag_service = RagService(db_session)

    # ---------- 节点1：解析用户任务（结构化输出 plan，驱动条件路由） ----------
    def parse_task(state: AgentState) -> dict:
        query = state["user_query"]

        default_plan = [
            {"task_type": "query_data", "description": f"查询「{query}」相关的历史火点与预测火险双数据源",
             "reason": "数据分析类任务默认需要真实数据", "required": True},
            {"task_type": "generate_report", "description": "基于数据生成分析报告",
             "reason": "默认输出分析报告", "required": True},
        ]
        if llm_available():
            prompt = f"""你是一个森林火险分析任务编排助手。系统对任何需求都会固定执行：
双数据源查询(query_data) → 空间分析(analyze_gis) → 生成分析报告(generate_report)，
分析报告是系统固定产出。你只需判断是否需要检索知识库。

用户需求：{query}

子任务类型：
- query_data: 查询历史火点(2021-2025)+预测火险(2025-2026)双数据源（固定执行，必须列出）
- analyze_gis: 空间分析（网格聚类+高风险识别，固定执行，必须列出）
- generate_report: 生成分析报告（固定执行，必须列出）
- retrieve_knowledge: 检索知识库（防火规范/应急预案等文档；仅当需求涉及条例/标准/预案/方法依据时列出）

请输出 JSON 对象：{{"plan": [{{"task_type": "...", "description": "...", "required": true}}, ...]}}
仅输出 JSON，不要其他文字。"""
            try:
                # P2#17 轻量化：意图解析输出为小体积 JSON，限 max_tokens 缩短首事件前的静默窗口
                plan_obj, meta = invoke_structured(prompt, TaskPlan, temperature=0.1, max_tokens=300,
                                                   fallback=_parse_plan_text)
                if plan_obj is not None and plan_obj.plan:
                    plan = [s.model_dump() for s in plan_obj.plan]
                else:
                    plan = default_plan
                # 审计信息：实际使用的 Provider / 模型 / 降级 / token
                audit = {}
                if meta is not None:
                    audit = {"llm_provider": meta.provider, "llm_model": meta.model,
                             "llm_degraded": meta.degraded}
                    if meta.tokens:
                        audit["tokens"] = meta.tokens
            except Exception:
                plan = default_plan
                audit = {}
        else:
            # 无 LLM 时生成默认计划
            plan = default_plan
            audit = {}

        # 计划归一化（硬约束，防 LLM 漏规划导致任务跑完无报告）：
        # query_data / analyze_gis / generate_report 为固定步骤，任何任务都必须产出报告；
        # LLM 计划仅用于决定是否追加 retrieve_knowledge（知识库检索）
        types = {s.get("task_type") for s in plan}
        kb_desc = next((s.get("description", "") for s in plan
                        if s.get("task_type") == "retrieve_knowledge"), "")
        plan = [
            {"task_type": "query_data", "required": True,
             "description": f"查询「{query}」相关的历史火点(2021-2025)与预测火险(2025-2026)双数据源",
             "reason": "双数据源查询为固定步骤"},
            {"task_type": "analyze_gis", "required": True,
             "description": "对查询结果做空间分析（历史0.1°网格聚类+预测高风险识别）",
             "reason": "有数据即执行空间分析"},
        ]
        if "retrieve_knowledge" in types:
            plan.append({"task_type": "retrieve_knowledge", "required": True,
                         "description": kb_desc or "检索知识库（防火规范/应急预案等文档）",
                         "reason": "需求涉及规范/预案依据"})
        plan.append({"task_type": "generate_report", "required": True,
                     "description": "汇总数据/空间分析/知识检索结果，生成分析报告",
                     "reason": "分析报告为系统固定产出"})

        step = {"step": "parse_task", "agent": "Orchestrator", "input": query,
                "output": {"plan": plan, **audit}, "status": "completed", "summary": "任务拆解完成"}
        return {"parsed_intent": {"plan": plan}, "steps": [step], "status": "parsed"}

    # ---------- 节点2：数据查询（双源 + 空结果反思重试，与 retrieve_knowledge 并行执行） ----------
    def _parse_query_params(query: str):
        """从查询文本提取年/月/城市/视图模式（初始参数）"""
        import re
        years = re.findall(r"(20\d{2})", query)
        month_m = re.search(r"(\d{1,2})月", query)
        month = int(month_m.group(1)) if month_m and 1 <= int(month_m.group(1)) <= 12 else None
        city = None
        from app.services.query_service import CITIES, SHORT_CITY_MAP
        for c in CITIES:
            if c in query:
                city = c
                break
        if not city:
            for short, full in SHORT_CITY_MAP.items():
                if short in query:
                    city = full
                    break
        year = int(years[0]) if len(years) == 1 else None
        view_mode = "daily" if any(k in query for k in ("逐日", "每日", "日报", "当天")) else "monthly"
        return year, month, city, view_mode

    def _run_dual_query(year, month, city, view_mode):
        """执行历史火点 + 预测火险双表查询（硬约束：只要查数必须双源）"""
        from app.schemas.dashboard import HistoryFireQuery, PredictRiskQuery
        from app.services.query_service import CITY_CENTERS

        # 1) 历史火点（historical_fire_points 表，覆盖 2021-2025）
        hq = HistoryFireQuery(
            start_date=f"{year}-01-01" if year else None,
            end_date=f"{year}-12-31" if year else None,
            city=city,
            page_size=5000,
        )
        hist = fire_repo.query_history_fires(hq)
        hist_items = []
        for it in hist.get("items", []):
            it = dict(it)
            it["source"] = "historical"
            hist_items.append(it)

        # 2) 预测火险（predicted_fire_risks 表，覆盖 2025-2026）
        pq = PredictRiskQuery(
            year=year if year and 2025 <= year <= 2026 else None,
            month=month if view_mode == "monthly" else None,
            view_mode=view_mode,
            city=city,
        )
        pred = fire_repo.query_predict_risks(pq)
        pred_items = []
        for it in pred.get("items", []):
            lng, lat = it.get("longitude"), it.get("latitude")
            if lng is None or lat is None:
                center = CITY_CENTERS.get(it.get("city"))
                if center:
                    lng, lat = center
            day = it.get("day")
            date_str = f"{it.get('year')}-{it.get('month'):02d}" + (f"-{day:02d}" if day else "")
            pred_items.append({
                "id": it.get("id"),
                "acq_date": date_str,
                "frp": it.get("pred_fire_risk") or it.get("pred_fire_count") or it.get("final_fire_index") or 0,
                "longitude": lng,
                "latitude": lat,
                "city": it.get("city"),
                "risk_score": it.get("risk_score"),
                "fire_level": it.get("fire_level"),
                "source": "predicted",
            })

        hist_total = hist.get("total", 0)
        pred_total = len(pred_items)
        data = {
            "status": "queried",
            "total": hist_total + pred_total,
            "hist_total": hist_total,
            "pred_total": pred_total,
            "items": hist_items + pred_items,
            "data_type": f"历史火点({hist_total})+预测火险({pred_total})",
        }
        return data, view_mode

    def _reflect_and_adjust(query, year, city, view_mode, tried):
        """LLM 反思：查询为空时建议放宽参数；返回 (year, city, view_mode) 或 None"""
        prompt = f"""森林火险数据查询结果为空，请分析原因并建议放宽后的查询参数。

用户需求：{query}
已尝试参数：{json.dumps(tried, ensure_ascii=False)}

数据范围说明：历史火点覆盖 2021-2025 年；预测火险覆盖 2025-2026 年。
请输出 JSON（null 表示该项不限/放宽）：
{{"reason": "无数据的可能原因", "adjusted_year": null, "adjusted_month": null,
  "adjusted_city": null, "adjusted_view_mode": "daily 或 monthly 或 null"}}
仅输出 JSON。"""
        try:
            adj, _meta = invoke_structured(prompt, QueryRetryPlan, temperature=0.2)
            if adj is None:
                return None
            new_year = adj.adjusted_year if adj.adjusted_year else None
            new_month = adj.adjusted_month if adj.adjusted_month else None
            new_city = adj.adjusted_city if adj.adjusted_city else None
            new_view = adj.adjusted_view_mode if adj.adjusted_view_mode else view_mode
            return new_year, new_month, new_city, new_view
        except Exception:
            return None

    def query_data(state: AgentState) -> dict:
        query = state["user_query"]
        year, month, city, view_mode = _parse_query_params(query)

        data = {"status": "no_data", "total": 0, "items": []}
        tried = []
        empty_reason = ""
        summary = ""
        for attempt in range(3):  # 初次查询 + 最多 2 轮反思重试
            try:
                data, view_mode = _run_dual_query(year, month, city, view_mode)
            except Exception as e:
                data = {"status": "error", "total": 0, "items": [], "error": str(e)}
                summary = f"DataAgent 查询失败: {str(e)[:50]}"
                break
            total = data.get("total", 0)
            tried.append({"year": year, "month": month, "city": city,
                          "view_mode": view_mode, "total": total})
            if total > 0:
                hist_total = data.get("hist_total", 0)
                pred_total = data.get("pred_total", 0)
                summary = (f"DataAgent 查询到 {hist_total} 条历史火点(覆盖2021-2025) "
                           f"+ {pred_total} 条{view_mode}预测火险(覆盖2025-2026)，"
                           f"共 {total} 条（均来自数据库）")
                break
            if attempt >= 2 or not llm_available():
                empty_reason = ("条件范围内无数据（含放宽重试）" if attempt > 0 else "条件范围内无数据")
                summary = f"DataAgent 未查询到数据（尝试 {len(tried)} 组参数）：{empty_reason}"
                break
            adjusted = _reflect_and_adjust(query, year, city, view_mode, tried)
            if adjusted is None:
                empty_reason = "LLM 反思不可用，无法调整查询参数"
                summary = f"DataAgent 未查询到数据（尝试 {len(tried)} 组参数）"
                break
            year, month, city, view_mode = adjusted

        output = {"total": data.get("total", 0),
                  "first_city": (data.get("items") or [{}])[0].get("city") if data.get("items") else None}
        if tried:
            output["attempts"] = tried
        if empty_reason:
            output["empty_reason"] = empty_reason
        step = {"step": "query_data", "agent": "DataAgent", "input": query,
                "output": output, "status": "completed", "summary": summary}
        return {"data_results": data, "steps": [step]}

    # ---------- 节点3：GIS 分析（历史火点网格聚类 + 预测数据高风险识别；计划未含或无数据时 no-op 跳过） ----------
    def analyze_gis(state: AgentState) -> dict:
        plan_types = {p.get("task_type") for p in (state.get("parsed_intent", {}).get("plan") or [])}
        data = state.get("data_results", {}) or {}

        if "analyze_gis" not in plan_types:
            step = {"step": "analyze_gis", "agent": "GisAgent",
                    "input": state["user_query"], "output": {"skipped": True, "reason": "计划未包含 GIS 分析"},
                    "status": "skipped", "summary": "计划未包含 GIS 分析，已跳过"}
            return {"gis_results": {"status": "skipped", "hotspots": [], "summary": "已跳过"}, "steps": [step]}
        if not data.get("items"):
            step = {"step": "analyze_gis", "agent": "GisAgent",
                    "input": state["user_query"], "output": {"skipped": True, "reason": "无数据可供空间分析"},
                    "status": "skipped", "summary": "无数据可供空间分析，已跳过"}
            return {"gis_results": {"status": "no_data", "hotspots": [], "summary": "无数据"}, "steps": [step]}

        gis = {"status": "no_data", "hotspots": [], "summary": "无数据"}
        try:
            items = data.get("items", []) or []
            hist_items = [i for i in items if i.get("source") != "predicted"]
            pred_items = [i for i in items if i.get("source") == "predicted"]
            hotspots = []
            hist_count = pred_count = 0
            if hist_items:
                h = asyncio_run(gis_agent.analyze_hotspots({"items": hist_items}))
                for x in h.get("hotspots", []):
                    x["kind"] = "历史聚类"
                hist_count = h.get("total_hotspots", 0)
                hotspots.extend(h.get("hotspots", []))
            if pred_items:
                p = asyncio_run(gis_agent.analyze_predicted({"items": pred_items}))
                for x in p.get("hotspots", []):
                    x["kind"] = "预测高风险"
                pred_count = p.get("total_hotspots", 0)
                hotspots.extend(p.get("hotspots", []))
            gis = {
                "status": "analyzed",
                "hotspots": hotspots[:40],
                "total_hotspots": hist_count + pred_count,
                "hist_hotspots": hist_count,
                "pred_hotspots": pred_count,
                "summary": f"识别到 {hist_count + pred_count} 个热点区域（历史聚类 {hist_count} 个 + 预测高风险 {pred_count} 个）",
            }
        except Exception as e:
            gis = {"status": "error", "hotspots": [], "summary": str(e)}

        step = {"step": "analyze_gis", "agent": "GisAgent",
                "input": f"对 {data.get('total', 0)} 条数据做空间分析（历史网格聚类+预测风险识别）",
                "output": {"hotspots": gis.get("hotspots", [])[:5],
                           "total_hotspots": gis.get("total_hotspots", 0)},
                "status": "completed",
                "summary": f"GisAgent 识别到 {gis.get('total_hotspots', 0)} 个热点区域"
                           f"（历史聚类 {gis.get('hist_hotspots', 0)} + 预测高风险 {gis.get('pred_hotspots', 0)}）"}
        return {"gis_results": gis, "steps": [step]}

    # ---------- 节点4：知识库检索（真实调用 RagAgent/RagService，与 query_data 并行执行） ----------
    def retrieve_knowledge(state: AgentState) -> dict:
        from app.agents.rag_agent import RagAgent
        rag_agent = RagAgent(rag_service)
        try:
            retri = asyncio_run(rag_agent.retrieve(state["user_query"], 5, user_id=user_id, is_admin=is_admin))
            # retri 现为 dict（含 items/method 等元数据）
            items = retri.get("items", [])
            knowledge = [
                {"document": r.get("document_title", "未知"),
                 "content": r.get("content", "")[:200],
                 "score": r.get("score", 0)}
                for r in items
            ]
            method = retri.get("method", "none")
            if retri.get("reranked"):
                method += "+rerank"
            step = {"step": "retrieve_knowledge", "agent": "RagAgent",
                    "input": state["user_query"],
                    "output": {"matched": len(items), "method": method},
                    "status": "completed",
                    "summary": f"RagAgent 在知识库命中 {len(items)} 个相关片段（{method}）"}
            return {"knowledge_results": knowledge, "steps": [step]}
        except Exception as e:
            step = {"step": "retrieve_knowledge", "agent": "RagAgent", "input": state["user_query"],
                    "output": {"error": str(e)}, "status": "failed",
                    "summary": f"RagAgent 检索失败: {str(e)[:50]}"}
            return {"knowledge_results": [], "steps": [step]}

    # ---------- 节点5：join 屏障（并行波次汇聚点，本身为 no-op） ----------
    def join(state: AgentState) -> dict:
        return {}

    # ---------- 节点6：生成报告（注入真实数据 + 评审意见/驳回意见重写） ----------
    def generate_report(state: AgentState) -> dict:
        query = state["user_query"]
        data = state.get("data_results", {}) or {}
        gis = state.get("gis_results", {}) or {}
        knowledge = state.get("knowledge_results", []) or []
        revisions = state.get("revisions", 0)
        review_fb = state.get("review_result", {}) or {}
        rejection = state.get("rejection_feedback", "") or ""

        # 汇总真实数据
        data_total = data.get("total", 0)
        hist_total = data.get("hist_total", 0)
        pred_total = data.get("pred_total", 0)
        items = data.get("items", []) or []
        top_cities = {}
        for it in items:
            c = it.get("city")
            if c:
                top_cities[c] = top_cities.get(c, 0) + 1
        top_cities_str = ", ".join(f"{c}({n})" for c, n in sorted(top_cities.items(), key=lambda x: -x[1])[:10]) or "无"

        hotspots = gis.get("hotspots", []) or []
        hotspot_str = "; ".join(
            (f"[{h.get('kind', '热点')}] " if h.get("kind") else "")
            + (f"{h.get('city')} " if h.get("city") else "")
            + f"[{h.get('lng', 0):.2f},{h.get('lat', 0):.2f}] 火点{h.get('count', 0)}个/平均FRP{h.get('avg_frp', 0)}"
            + (f"/风险评分{h.get('risk_score', 0)}" if h.get("risk_score") is not None else "")
            for h in hotspots[:12]
        ) or "无"

        kb_str = "\n".join(
            f"- （{k.get('document', '未知')}，相关度{k.get('score', 0)}）{k.get('content', '')[:150]}"
            for k in knowledge[:5]
        ) or "无"

        empty_reason = ""
        q_out = {}
        for s in reversed(state.get("steps", [])):
            if s.get("step") == "query_data":
                q_out = s.get("output", {}) or {}
                break
        if q_out.get("empty_reason"):
            empty_reason = q_out["empty_reason"]

        # P2#14：重点区域实时天气（MCP 高德只读数据源；未启用/依赖缺失/调用失败静默跳过）
        weather_str = ""
        if settings.MCP_ENABLED and (hotspots or items):
            try:
                from app.core.mcp_client import get_weather_for_city
                _city = ((hotspots[0].get("city") if hotspots else None)
                         or (items[0].get("city") if items else None))
                if _city:
                    weather_str = get_weather_for_city(_city)
            except Exception:
                weather_str = ""

        # P2#15：用户分析偏好（PostgresStore 长期记忆；未启用/无记录时为空，失败静默）
        prefs_str = ""
        if settings.PREFERENCES_ENABLED and user_id is not None:
            try:
                from app.core.memory_store import prefs_context
                prefs_str = prefs_context(user_id)
            except Exception:
                prefs_str = ""

        # 评审意见 / 用户驳回意见（重写轮注入）
        revise_hint = ""
        if review_fb.get("issues") or review_fb.get("suggestion"):
            issues_str = "\n".join(f"  - {i}" for i in (review_fb.get("issues") or []))
            revise_hint += (f"\n## 评审意见（上一稿未通过评审，必须针对性修改）\n"
                            f"发现的问题：\n{issues_str or '  - 无'}\n"
                            f"修改建议：{review_fb.get('suggestion', '') or '无'}\n")
        if rejection:
            revise_hint += f"\n## 用户驳回意见（必须吸收进本稿）\n{rejection}\n"

        if llm_available():
            prompt = f"""你是资深森林防火专家（ReportAgent），为森林防火指挥中心撰写正式分析报告。请根据以下多 Agent 协作产出的真实数据，撰写一份**详尽、专业、直击重点**的 Markdown 分析报告。

用户需求：{query}

## DataAgent 查询结果（真实数据库数据）
- 数据构成：历史火点 {hist_total} 条（覆盖2021-2025，NASA FIRMS 卫星观测）+ 预测火险 {pred_total} 条（覆盖2025-2026，模型预测）
- 记录总数：{data_total} 条
- 火点/风险分布（按州市统计）：{top_cities_str}
{('- 数据为空原因：' + empty_reason + chr(10)) if empty_reason else ''}
## GisAgent 空间分析结果
- 热点区域明细：{hotspot_str}
{('- 重点区域实时天气（MCP 高德数据源）：' + weather_str + chr(10)) if weather_str else ''}

## RagAgent 知识库检索（防火规范/预案参考）
{ kb_str }
{revise_hint}{(chr(10) + '## 用户分析偏好（历史查询习惯，巡防建议尽量贴合其辖区与关注时段）' + chr(10) + prefs_str + chr(10)) if prefs_str else ''}
## 报告模板（强制：所有报告必须一字不差地套用以下固定模板，章节标题、顺序、数量都不可改动）
# 云南森林火险分析报告
## 一、执行摘要
（用「1. 2. 3.」分条列出 3-5 条核心结论：哪里最危险（州市/热点名）、为什么（数据依据）、建议干什么）
## 二、数据来源与分析方法
（分条列举：历史火点数据源与时间范围、预测数据源与模型口径、空间分析方法、天气数据源；每条注明数据时间口径）
## 三、火情数据分析
（先用 Markdown 表格呈现「表 1：各州市火点/风险统计」（列：州市、历史火点数、预测风险数、风险等级），表格下方必须有「表 1 说明：」段落解读数据揭示的规律；再分条详述高发区域与时段规律，每条先给数字后阐释成因）
## 四、高风险区域识别
（逐个热点区域分条列举，每条格式「N. 所属州市[坐标]：火点数/平均FRP/风险评分——成因阐释」；区域定位必须使用数据中标注的所属州市名称，**严禁仅凭经纬度自行推断地名**；植被、地形类成因若无数据或知识库支撑，写明「待实地核查」，禁止臆断）
## 五、重点巡防建议
（分区域分条给出可执行措施——巡防时段（结合火险等级）、重点地段、卡口设置、瞭望监测、力量部署、物资准备、宣传管控；每条建议后用一句话说明依据）
## 六、结论与展望
## 附：参考依据
（编号列举所有引用来源，每条注明来源类型（知识库文档/历史火点统计/模型预测/高德实时天气）+ 名称或片段主题 + 相似度/时间口径；无检索结果时写明"本次未检索到匹配知识库文档"）

## 撰写要求（必须严格遵守）
1. **所有数字必须直接引用上面的真实数据**，禁止编造；数据为 0 的部分要说明原因（如该时段无历史记录、以预测数据为准）。
2. **模板刚性**：上面是唯一合法的报告结构——七个章节的标题文字与顺序完全固定，每章必须有内容（数据为空时写明原因），不得省略、合并、改名或新增章节。
3. **表达形式**：全文以分条列举为主，每条做到「结论 + 数据 + 阐释」三要素齐全；关键统计必须用 Markdown 表格呈现并配「表 N 说明」图注文字；禁止整段泛泛而谈。
4. 篇幅要求：**不少于 800 字**，重点区域分析要具体到州市名称和数据，巡防建议要能直接落地执行。
5. 语言风格：正式公文风格，直接陈述，不用客套话。
6. 报告头部的「报告生成时间」由系统自动注入，无需你撰写任何时间信息。

仅输出 Markdown 报告正文。"""
            try:
                res = None
                if settings.LLM_STREAM_ENABLED and task_id is not None:
                    # P2#18 流式生成（增量经 report_channels 实时推送 SSE）；失败/0 字符返回 None 走非流式兜底
                    res = _stream_report(prompt, task_id)
                    if res is not None and not (res.text or "").strip():
                        res = None  # 流式 0 字符（思考型模型 content 为空等）→ 必须兜底重试
                if res is None:
                    res = invoke_llm(prompt, temperature=0.4, max_tokens=4000,
                                     enable_thinking=False)
                if res is not None and (res.text or "").strip():
                    report = res.text
                    audit = {"llm_provider": res.provider, "llm_model": res.model,
                             "llm_degraded": res.degraded}
                    if res.tokens:
                        audit["tokens"] = res.tokens
                else:
                    # 所有 Provider 均不可用或均返回空内容 → 模板兜底，保证报告正文永不为空
                    report = _template_report(query, data_total, hist_total, pred_total,
                                              top_cities_str, hotspot_str, kb_str)
                    audit = {}
            except Exception as e:
                report = _template_report(query, data_total, hist_total, pred_total,
                                          top_cities_str, hotspot_str, kb_str) + f"\n\n> LLM 调用异常：{e}"
                audit = {}
        else:
            report = _template_report(query, data_total, hist_total, pred_total,
                                      top_cities_str, hotspot_str, kb_str)
            audit = {}

        summary = f"ReportAgent 生成 {len(report)} 字符报告"
        if revisions > 0:
            summary += f"（第 {revisions} 轮修订）"
        step = {"step": "generate_report", "agent": "ReportAgent", "input": query,
                "output": {"report_length": len(report), **audit}, "status": "completed",
                "summary": summary}
        # 系统注入报告生成时间（不依赖 LLM，避免时间幻觉）；统一追加系统署名（开发者信息 + 项目地址）
        from datetime import datetime
        generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        report = (f"> 报告生成时间：{generated_at} ｜ 数据构成：历史火点 {hist_total} 条 · 预测火险 {pred_total} 条\n\n"
                  + report + settings.REPORT_FOOTER)
        return {"report": report, "steps": [step], "status": "completed"}

    # ---------- 节点7：质量评审（LLM 评审 + 硬护栏；不通过带意见回 generate_report，最多 2 轮） ----------
    def review_report(state: AgentState) -> dict:
        report = state.get("report", "")
        revisions = state.get("revisions", 0)

        # 硬护栏（不依赖 LLM，一票否决）
        issues = []
        core = report.replace(settings.REPORT_FOOTER, "")
        if len(core.strip()) < 800:
            issues.append(f"报告正文仅 {len(core.strip())} 字符，要求不少于 800 字符")
        if "执行摘要" not in report:
            issues.append("缺少「执行摘要」章节")
        if "巡防" not in report:
            issues.append("缺少巡防建议相关内容")
        data = state.get("data_results", {}) or {}
        for label, key in (("历史火点", "hist_total"), ("预测火险", "pred_total")):
            v = data.get(key, 0)
            if v > 0 and str(v) not in report:
                issues.append(f"报告未引用{label}真实数据（{v} 条）")

        # LLM 评审（低温度）
        suggestion = ""
        if llm_available():
            prompt = f"""你是严格的分析报告质量评审员（Reviewer）。请评审以下森林火险分析报告。

评审标准：
1. 结构完整（执行摘要/数据分析/风险识别/巡防建议等章节）
2. 数据引用真实（数字与给定数据一致，无编造）
3. 巡防建议具体可执行（分区域、有时段、有措施）

报告内容：
{report[:4000]}

返回 JSON：{{"passed": true/false, "issues": ["问题1", "问题2"], "suggestion": "针对性修改建议"}}
仅输出 JSON。"""
            try:
                verdict, _meta = invoke_structured(prompt, ReviewVerdict, temperature=0.0)
                if verdict is not None:
                    for i in (verdict.issues or []):
                        if i and i not in issues:
                            issues.append(i)
                    suggestion = verdict.suggestion or ""
                    passed = bool(verdict.passed) and not issues  # 硬护栏一票否决
                else:
                    passed = not issues
                    suggestion = "结构化评审不可用，按硬护栏判定"
            except Exception:
                passed = not issues
                suggestion = "评审 LLM 调用异常，按硬护栏判定"
        else:
            passed = not issues
            suggestion = "LLM 不可用，按硬护栏判定"

        review = {"passed": passed, "issues": issues, "suggestion": suggestion}
        if passed:
            summary = "Reviewer 评审通过" + (f"（{len(issues)} 项提示）" if issues else "")
        elif revisions < 2:
            summary = f"Reviewer 评审未通过（{len(issues)} 项问题），退回 ReportAgent 重写"
        else:
            review["forced"] = True
            summary = f"Reviewer 评审未通过但已达重写上限（{revisions} 轮），强制放行并在结果中标注"

        step = {"step": "review_report", "agent": "Reviewer", "input": f"评审报告（{len(report)} 字符）",
                "output": {"passed": passed, "issues": issues[:5], "suggestion": suggestion[:100],
                           "revisions": revisions},
                "status": "completed" if passed else "failed",
                "summary": summary}
        result = {"review_result": review, "steps": [step]}
        if not passed and revisions < 2:
            result["revisions"] = revisions + 1
        return result

    # ---------- 节点8：HITL 审批闸口（interrupt 暂停，等待 resume 注入人工决策） ----------
    def approval_gate(state: AgentState) -> dict:
        from langgraph.types import interrupt
        draft = state.get("report", "")
        review = state.get("review_result", {}) or {}
        resume = interrupt({
            "report": draft,
            "review": review,
            "revisions": state.get("revisions", 0),
        })
        resume = resume or {}
        action = resume.get("action", "approve")

        if action == "edit":
            content = resume.get("content") or draft
            step = {"step": "approval", "agent": "HITL", "input": state["user_query"],
                    "output": {"action": "edit", "content_length": len(content)},
                    "status": "completed", "summary": "人工审批：编辑后通过"}
            return {"report": content, "decision": "edit", "status": "completed", "steps": [step]}
        if action == "reject":
            comment = resume.get("comment", "") or ""
            step = {"step": "approval", "agent": "HITL", "input": state["user_query"],
                    "output": {"action": "reject", "comment": comment[:200]},
                    "status": "completed", "summary": f"人工驳回：{comment[:50]}"}
            return {"decision": "reject", "rejection_feedback": comment, "revisions": 0, "steps": [step]}
        step = {"step": "approval", "agent": "HITL", "input": state["user_query"],
                "output": {"action": "approve"},
                "status": "completed", "summary": "人工审批：通过"}
        return {"decision": "approve", "status": "completed", "steps": [step]}

    return parse_task, query_data, analyze_gis, retrieve_knowledge, join, generate_report, review_report, approval_gate


def _template_report(query, data_total, hist_total, pred_total, top_cities, hotspot, kb) -> str:
    """无 LLM 时的模板报告（仍含真实数据，结构完整）"""
    return f"""# 火险分析报告

## 一、执行摘要
基于用户查询「{query}」，系统完成 DataAgent（数据查询）→ GisAgent（空间分析）→ RagAgent（知识检索）多 Agent 协作分析，共获取 {data_total} 条真实数据并识别风险区域，具体如下。

## 二、数据来源与分析方法
- 历史火点数据：{hist_total} 条（NASA FIRMS 卫星观测，覆盖2021-2025）
- 预测火险数据：{pred_total} 条（模型预测，覆盖2025-2026）
- 分析方法：历史火点经纬度 0.1° 网格聚类识别聚集区；预测数据按火险等级识别高风险州市

## 三、火情数据分析
- 记录总数：{data_total} 条
- 火点/风险分布（按州市统计）：{top_cities}

## 四、高风险区域识别
- 热点区域明细：{hotspot}

## 五、重点巡防建议
1. 对上述热点区域所在的州市提高巡查频次，火险等级 4 级以上区域实行每日巡护；
2. 在高火险时段（10:00-18:00）加强瞭望监测与卡口检查；
3. 预置扑火队伍与物资至重点乡镇，检查风力灭火机、水泵等装备；
4. 结合知识库规范开展防火宣传与野外用火管控。

## 附：参考依据（RagAgent）
{ kb if kb != "无" else "- 知识库未命中相关内容" }

> 注：LLM 未配置，此报告由模板生成但包含真实检索与分析数据。"""


def asyncio_run(coro):
    """同步环境中执行协程"""
    import asyncio
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop and loop.is_running():
        # 已在事件循环内（FastAPI async 上下文）→ 用新循环跑
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(1) as ex:
            return ex.submit(asyncio.run, coro).result()
    return asyncio.run(coro)


# ===== 条件路由函数（模块级纯函数：只读 parsed_intent.plan / review_result / decision，不读并行节点写入的键） =====

def route_after_parse(state: AgentState) -> list[str]:
    """parse_task 后的并行 fan-out：按计划并行触发 query_data 与 retrieve_knowledge"""
    plan = (state.get("parsed_intent", {}) or {}).get("plan") or []
    types = {p.get("task_type") for p in plan}
    targets = []
    if "query_data" in types:
        targets.append("query_data")
    if "retrieve_knowledge" in types:
        targets.append("retrieve_knowledge")
    if not targets:
        # 兜底：默认执行数据查询（双源查询硬约束）
        targets = ["query_data"]
    return targets


def route_after_join(state: AgentState) -> Literal["generate_report", "end"]:
    """join 后按计划决定是否生成报告"""
    plan = (state.get("parsed_intent", {}) or {}).get("plan") or []
    types = {p.get("task_type") for p in plan}
    if "generate_report" in types:
        return "generate_report"
    return "end"


def route_after_review(state: AgentState) -> Literal["generate_report", "approval_gate", "end"]:
    """评审后：不通过且未达上限 → 重写；通过（或强制放行）→ 审批闸口 / 结束"""
    review = state.get("review_result", {}) or {}
    if not review.get("passed") and state.get("revisions", 0) < 2 and not review.get("forced"):
        return "generate_report"
    if settings.AGENT_REQUIRE_APPROVAL:
        return "approval_gate"
    return "end"


def route_after_approval(state: AgentState) -> Literal["generate_report", "end"]:
    """审批后：reject → 按驳回意见重写；approve/edit → 结束"""
    if state.get("decision") == "reject":
        return "generate_report"
    return "end"


# ===== 构建 LangGraph 图 =====

def build_workflow_graph(nodes: list[Callable], checkpointer=None) -> "CompiledStateGraph":
    """构建 LangGraph StateGraph（P1 拓扑：fan-out/join + 评审循环 + 审批闸口）

    图拓扑：
      parse_task →(条件fan-out)→ [query_data?, retrieve_knowledge?]
      query_data → analyze_gis → join
      retrieve_knowledge → join
      join →(条件)→ generate_report | END
      generate_report → review_report →(条件)→ generate_report(重写) / approval_gate / END
      approval_gate →(条件)→ generate_report(驳回重写) / END
    """
    from langgraph.graph import StateGraph, END

    workflow = StateGraph(AgentState)
    (parse_task, query_data, analyze_gis, retrieve_knowledge,
     join, generate_report, review_report, approval_gate) = nodes

    workflow.add_node("parse_task", parse_task)
    workflow.add_node("query_data", query_data)
    workflow.add_node("analyze_gis", analyze_gis)
    workflow.add_node("retrieve_knowledge", retrieve_knowledge)
    workflow.add_node("join", join)
    workflow.add_node("generate_report", generate_report)
    workflow.add_node("review_report", review_report)
    workflow.add_node("approval_gate", approval_gate)

    workflow.set_entry_point("parse_task")

    # 并行 fan-out：路由函数返回 list 时 LangGraph 并行触发多个分支
    workflow.add_conditional_edges("parse_task", route_after_parse, {
        "query_data": "query_data",
        "retrieve_knowledge": "retrieve_knowledge",
    })
    workflow.add_edge("query_data", "analyze_gis")       # 计划未含时 analyze_gis 内部 no-op 跳过
    workflow.add_edge("analyze_gis", "join")
    workflow.add_edge("retrieve_knowledge", "join")
    workflow.add_conditional_edges("join", route_after_join, {
        "generate_report": "generate_report",
        "end": END,
    })
    workflow.add_edge("generate_report", "review_report")
    workflow.add_conditional_edges("review_report", route_after_review, {
        "generate_report": "generate_report",
        "approval_gate": "approval_gate",
        "end": END,
    })
    workflow.add_conditional_edges("approval_gate", route_after_approval, {
        "generate_report": "generate_report",
        "end": END,
    })

    return workflow.compile(checkpointer=checkpointer)


# ===== 编排器对外接口 =====

def _initial_state(user_query: str) -> AgentState:
    """构造任务初始状态（execute 与 stream 共用，保证两接口行为一致）"""
    return AgentState(
        user_query=user_query,
        parsed_intent={},
        data_results={},
        gis_results={},
        knowledge_results=[],
        report="",
        status="pending",
        steps=[],
        error=None,
        revisions=0,
        review_result={},
        decision="",
        rejection_feedback="",
    )


class OrchestratorAgent:
    """任务编排 Agent（依赖 db session 构造真实节点）

    checkpointer：每实例独享（PostgresSaver 单连接非线程安全，禁止跨实例共享）。
    thread_id 按任务固定（task-{id}），HITL 中断态由 checkpointer 持久化，
    resume 时用同 thread_id 重建实例并 stream(Command(resume=...)) 即可续跑。
    """

    def __init__(self, db_session=None, user_id=None, is_admin=False, thread_id: str | None = None,
                 task_id: int | None = None):
        self.db = db_session
        self.user_id = user_id
        self.is_admin = is_admin
        self.thread_id = thread_id
        self.task_id = task_id
        self.checkpointer = create_checkpointer()
        nodes = (_make_nodes(db_session, user_id=user_id, is_admin=is_admin, task_id=task_id)
                 if db_session is not None else _make_fallback_nodes())
        self.graph = build_workflow_graph(nodes, checkpointer=self.checkpointer)

    def snapshot_state(self) -> dict:
        """取当前 thread 在 checkpointer 中的累积状态（HITL 恢复时必须先调用）

        stream(Command(resume=...)) 只产出中断之后的增量，若从空字典开始累积，
        中断前已生成的 report/steps/data_results 全部丢失（报告将无法落库）。
        """
        try:
            snap = self.graph.get_state(self._config())
            return dict(snap.values or {})
        except Exception:
            return {}

    def _config(self) -> dict:
        """LangGraph 运行配置（thread_id 用于 checkpoint 状态隔离）

        P2#12：启用 Langfuse 时附加观测 callbacks（未启用/未部署返回 None，无副作用）
        """
        cfg = {"configurable": {"thread_id": self.thread_id or "default"}}
        try:
            from app.core.observability import build_callback_config
            obs = build_callback_config(task_id=self.task_id, thread_id=self.thread_id)
            if obs:
                cfg.update(obs)
        except Exception:
            pass
        return cfg

    async def execute(self, user_query: str) -> dict[str, Any]:
        """执行完整分析流程（一次性返回最终结果，兼容旧调用方）"""
        result = self.graph.invoke(_initial_state(user_query), self._config())
        return {
            "report": result.get("report", ""),
            "steps": result.get("steps", []),
            "status": result.get("status", "failed"),
            "llm_used": llm_available(),
            "data": result.get("data_results", {}),
            "gis": result.get("gis_results", {}),
            "knowledge": result.get("knowledge_results", []),
        }

    def iter_steps(self, user_query: str):
        """逐步执行（生成器）：yield (节点名或"__interrupt__", 该节点返回的状态增量)

        供后台 worker 流式落库步骤 + SSE 推送进度；遇到 interrupt 时 yield
        ("__interrupt__", (Interrupt(...),))，由调用方决定暂停/恢复。
        """
        for event in self.graph.stream(_initial_state(user_query), self._config(),
                                       stream_mode="updates"):
            for node_name, update in (event or {}).items():
                yield node_name, update or {}

    def iter_resume(self, resume_value: dict):
        """从 HITL 中断点恢复执行：yield (节点名或"__interrupt__", 状态增量)

        resume_value 为人工决策：{"action": "approve"|"edit"|"reject", "content": str, "comment": str}
        """
        from langgraph.types import Command
        for event in self.graph.stream(Command(resume=resume_value), self._config(),
                                       stream_mode="updates"):
            for node_name, update in (event or {}).items():
                yield node_name, update or {}


def _make_fallback_nodes():
    """无 db 时的兜底节点（保持新图结构可用，返回占位数据；同样只返回 delta）"""
    def parse_task(state: AgentState) -> dict:
        plan = [
            {"task_type": "query_data", "description": "默认计划（数据库未连接）", "required": True},
            {"task_type": "generate_report", "description": "生成模板报告", "required": True},
        ]
        step = {"step": "parse_task", "agent": "Orchestrator", "input": state["user_query"],
                "output": {"plan": plan},
                "status": "completed", "summary": "任务拆解完成（数据库未连接）"}
        return {"parsed_intent": {"plan": plan}, "steps": [step], "status": "parsed"}

    def query_data(state: AgentState) -> dict:
        step = {"step": "query_data", "agent": "DataAgent", "input": state["user_query"],
                "output": {"error": "数据库未连接"}, "status": "failed",
                "summary": "DataAgent 无法查询（数据库未连接）"}
        return {"data_results": {"status": "no_db", "total": 0, "items": []}, "steps": [step]}

    def analyze_gis(state: AgentState) -> dict:
        step = {"step": "analyze_gis", "agent": "GisAgent", "input": state["user_query"],
                "output": {"skipped": True, "reason": "无数据"}, "status": "skipped",
                "summary": "GisAgent 无数据可分析，已跳过"}
        return {"gis_results": {"status": "no_data", "hotspots": [], "summary": "无数据"}, "steps": [step]}

    def retrieve_knowledge(state: AgentState) -> dict:
        step = {"step": "retrieve_knowledge", "agent": "RagAgent", "input": state["user_query"],
                "output": {"matched": 0}, "status": "completed", "summary": "RagAgent 无知识库可检索"}
        return {"knowledge_results": [], "steps": [step]}

    def join(state: AgentState) -> dict:
        return {}

    def generate_report(state: AgentState) -> dict:
        report = _template_report(state["user_query"], 0, 0, 0, "无", "无", "无") + settings.REPORT_FOOTER
        step = {"step": "generate_report", "agent": "ReportAgent", "input": state["user_query"],
                "output": {"report_length": len(report)}, "status": "completed",
                "summary": "ReportAgent 生成报告（无数据库）"}
        return {"report": report, "steps": [step], "status": "completed"}

    def review_report(state: AgentState) -> dict:
        review = {"passed": True, "issues": [], "suggestion": "无 LLM 环境，跳过评审"}
        step = {"step": "review_report", "agent": "Reviewer", "input": "模板报告",
                "output": {"passed": True}, "status": "completed",
                "summary": "Reviewer 评审通过（无 LLM，硬护栏跳过）"}
        return {"review_result": review, "steps": [step]}

    def approval_gate(state: AgentState) -> dict:
        # 无 db 场景（内部工具/测试）不做真实 HITL，自动通过
        step = {"step": "approval", "agent": "HITL", "input": state["user_query"],
                "output": {"action": "auto_approve"}, "status": "completed",
                "summary": "审批闸口：无数据库环境自动通过"}
        return {"decision": "approve", "status": "completed", "steps": [step]}

    return parse_task, query_data, analyze_gis, retrieve_knowledge, join, generate_report, review_report, approval_gate
