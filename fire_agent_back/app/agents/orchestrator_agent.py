"""
编排 Agent — 使用 LangGraph StateGraph 做任务编排

中间节点（query_data / analyze_gis / retrieve_knowledge）真实调用
DataAgent / GisAgent / RagAgent，并把真实结果注入报告 Prompt，
报告内容包含真实的统计数据、热点区域、知识库片段。
"""
import json
from typing import TYPE_CHECKING, Any, TypedDict, Literal, Callable

from app.core.config import settings

from app.core.llm import get_llm, llm_available

# 仅用于类型检查解析，避免运行时强制导入 langgraph（保持懒加载、加快启动）
if TYPE_CHECKING:
    from langgraph.graph import CompiledStateGraph


# ===== LangGraph 状态定义 =====
class AgentState(TypedDict):
    """Agent 工作流状态"""
    user_query: str
    parsed_intent: dict
    data_results: dict
    gis_results: dict
    knowledge_results: list
    report: str
    status: str
    steps: list[dict]
    error: str | None


# ===== 节点工厂（注入 db session 依赖） =====

def _make_nodes(db_session, user_id=None, is_admin=False):
    """构造依赖 db 的节点函数（闭包），使 LangGraph 节点能访问数据库"""
    from app.repositories.fire_repository import FireRepository
    from app.agents.gis_agent import GisAgent
    from app.services.rag_service import RagService

    fire_repo = FireRepository(db_session)
    gis_agent = GisAgent()
    rag_service = RagService(db_session)

    # ---------- 节点1：解析用户任务 ----------
    def parse_task(state: AgentState) -> dict:
        query = state["user_query"]
        steps = state.get("steps", [])

        if llm_available():
            llm = get_llm(temperature=0.1)
            prompt = f"""你是一个森林火险分析任务编排助手。请将用户的需求拆解为子任务列表。

用户需求：{query}

可用子任务类型：
- query_data: 查询历史火点或预测火险数据
- analyze_gis: 空间分析（缓冲区、热区识别）
- retrieve_knowledge: 检索知识库（防火规范、应急预案）
- generate_report: 生成分析报告

请输出 JSON 数组，每个元素包含 task_type 和 description：
[{{"task_type": "query_data", "description": "..."}}, ...]
仅输出 JSON，不要其他文字。"""
            try:
                resp = llm.invoke(prompt)
                text = resp.content if hasattr(resp, "content") else str(resp)
                text = text.strip().removeprefix("```json").removesuffix("```").strip()
                plan = json.loads(text)
            except Exception:
                plan = [{"task_type": "query_data", "description": f"查询{query}相关数据"}]
        else:
            # 无 LLM 时生成默认计划
            plan = [{"task_type": "query_data", "description": f"查询{query}相关数据"}]

        steps.append({"step": "parse_task", "agent": "Orchestrator", "input": query,
                      "output": {"plan": plan}, "status": "completed", "summary": "任务拆解完成"})
        return {"parsed_intent": {"plan": plan}, "steps": steps, "status": "parsed"}

    # ---------- 节点2：数据查询（真实调用 DataAgent，支持历史火点/预测火险） ----------
    def query_data(state: AgentState) -> dict:
        from app.schemas.dashboard import HistoryFireQuery, PredictRiskQuery
        steps = state.get("steps", [])
        query = state["user_query"]
        data = {"status": "no_data", "total": 0, "items": []}
        try:
            import re
            years = re.findall(r"(20\d{2})", query)
            month_m = re.search(r"(\d{1,2})月", query)
            month = int(month_m.group(1)) if month_m and 1 <= int(month_m.group(1)) <= 12 else None
            city = None
            from app.services.query_service import CITIES, SHORT_CITY_MAP, CITY_CENTERS
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

            # 2) 预测火险（predicted_fire_risks 表，覆盖 2025-2026；双源查询避免漏数据）
            view_mode = "daily" if any(k in query for k in ("逐日", "每日", "日报", "当天")) else "monthly"
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
            summary = (f"DataAgent 查询到 {hist_total} 条历史火点(覆盖2021-2025) "
                       f"+ {pred_total} 条{view_mode}预测火险(覆盖2025-2026)，"
                       f"共 {hist_total + pred_total} 条（均来自数据库）")
        except Exception as e:
            data = {"status": "error", "total": 0, "items": [], "error": str(e)}
            summary = f"DataAgent 查询失败: {str(e)[:50]}"

        steps.append({"step": "query_data", "agent": "DataAgent", "input": query,
                      "output": {"total": data.get("total", 0),
                                 "first_city": (data.get("items") or [{}])[0].get("city") if data.get("items") else None},
                      "status": "completed",
                      "summary": summary})
        return {"data_results": data, "steps": steps, "status": "data_ready"}

    # ---------- 节点3：GIS 分析（历史火点网格聚类 + 预测数据高风险识别，双源合并） ----------
    def analyze_gis(state: AgentState) -> dict:
        steps = state.get("steps", [])
        data = state.get("data_results", {}) or {}
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

        steps.append({"step": "analyze_gis", "agent": "GisAgent",
                      "input": f"对 {state.get('data_results', {}).get('total', 0)} 条数据做空间分析（历史网格聚类+预测风险识别）",
                      "output": {"hotspots": gis.get("hotspots", [])[:5],
                                 "total_hotspots": gis.get("total_hotspots", 0)},
                      "status": "completed",
                      "summary": f"GisAgent 识别到 {gis.get('total_hotspots', 0)} 个热点区域"
                                 f"（历史聚类 {gis.get('hist_hotspots', 0)} + 预测高风险 {gis.get('pred_hotspots', 0)}）"})
        return {"gis_results": gis, "steps": steps, "status": "gis_ready"}

    # ---------- 节点4：知识库检索（真实调用 RagAgent/RagService） ----------
    def retrieve_knowledge(state: AgentState) -> dict:
        from app.agents.rag_agent import RagAgent
        steps = state.get("steps", [])
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
            steps.append({"step": "retrieve_knowledge", "agent": "RagAgent",
                          "input": state["user_query"],
                          "output": {"matched": len(items), "method": retri.get("method", "none")},
                          "status": "completed",
                          "summary": f"RagAgent 在知识库命中 {len(items)} 个相关片段（{retri.get('method', 'none')}）"})
            return {"knowledge_results": knowledge, "steps": steps, "status": "knowledge_ready"}
        except Exception as e:
            steps.append({"step": "retrieve_knowledge", "agent": "RagAgent", "input": state["user_query"],
                          "output": {"error": str(e)}, "status": "failed",
                          "summary": f"RagAgent 检索失败: {str(e)[:50]}"})
            return {"knowledge_results": [], "steps": steps, "status": "knowledge_ready"}

    # ---------- 节点5：生成报告（注入真实数据） ----------
    def generate_report(state: AgentState) -> dict:
        query = state["user_query"]
        steps = state.get("steps", [])
        data = state.get("data_results", {}) or {}
        gis = state.get("gis_results", {}) or {}
        knowledge = state.get("knowledge_results", []) or []

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

        if llm_available():
            llm = get_llm(temperature=0.4, max_tokens=4000)
            prompt = f"""你是资深森林防火专家（ReportAgent），为森林防火指挥中心撰写正式分析报告。请根据以下多 Agent 协作产出的真实数据，撰写一份**详尽、专业、直击重点**的 Markdown 分析报告。

用户需求：{query}

## DataAgent 查询结果（真实数据库数据）
- 数据构成：历史火点 {hist_total} 条（覆盖2021-2025，NASA FIRMS 卫星观测）+ 预测火险 {pred_total} 条（覆盖2025-2026，模型预测）
- 记录总数：{data_total} 条
- 火点/风险分布（按州市统计）：{top_cities_str}

## GisAgent 空间分析结果
- 热点区域明细：{hotspot_str}

## RagAgent 知识库检索（防火规范/预案参考）
{ kb_str }

## 撰写要求（必须严格遵守）
1. **所有数字必须直接引用上面的真实数据**，禁止编造；数据为 0 的部分要说明原因（如该时段无历史记录、以预测数据为准）。
2. 报告结构（Markdown，用二级/三级标题）：
   - 一、执行摘要：3-5 句话点明核心结论（哪里最危险、为什么、建议干什么）
   - 二、数据来源与分析方法：说明历史/预测双数据源构成与分析流程
   - 三、火情数据分析：分州市引用统计数字，指出高发区域和时段规律
   - 四、高风险区域识别：逐一分析每个热点区域（位置、火点数/风险评分、风险成因）
   - 五、重点巡防建议：**分区域给出可执行的具体措施**——巡防时段（结合火险等级）、重点地段、卡口设置、瞭望监测、力量部署、物资准备、宣传管控
   - 六、结论与展望
   - 附：参考依据（引用知识库片段与相关度）
3. 篇幅要求：**不少于 800 字**，重点区域分析要具体到州市名称和数据，巡防建议要能直接落地执行。
4. 语言风格：正式公文风格，直接陈述，不用客套话。

仅输出 Markdown 报告正文。"""
            try:
                resp = llm.invoke(prompt)
                report = resp.content if hasattr(resp, "content") else str(resp)
            except Exception as e:
                report = _template_report(query, data_total, hist_total, pred_total,
                                          top_cities_str, hotspot_str, kb_str) + f"\n\n> LLM 调用异常：{e}"
        else:
            report = _template_report(query, data_total, hist_total, pred_total,
                                      top_cities_str, hotspot_str, kb_str)

        steps.append({"step": "generate_report", "agent": "ReportAgent", "input": query,
                      "output": {"report_length": len(report)}, "status": "completed",
                      "summary": f"ReportAgent 生成 {len(report)} 字符报告"})
        # 统一追加系统署名（开发者信息 + 项目地址）
        report = report + settings.REPORT_FOOTER
        return {"report": report, "steps": steps, "status": "completed"}

    return parse_task, query_data, analyze_gis, retrieve_knowledge, generate_report


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


def should_continue(state: AgentState) -> Literal["query_data", "analyze_gis", "retrieve_knowledge", "generate_report", "end"]:
    """条件边：根据状态决定下一步"""
    s = state["status"]
    if s == "parsed":
        return "query_data"
    elif s == "data_ready":
        return "analyze_gis"
    elif s == "gis_ready":
        return "retrieve_knowledge"
    elif s == "knowledge_ready":
        return "generate_report"
    return "end"


# ===== 构建 LangGraph 图 =====

def build_workflow_graph(nodes: list[Callable]) -> "CompiledStateGraph":
    """构建 LangGraph StateGraph（节点函数由 _make_nodes 注入 db 依赖）"""
    from langgraph.graph import StateGraph, END

    workflow = StateGraph(AgentState)
    parse_task, query_data, analyze_gis, retrieve_knowledge, generate_report = nodes

    workflow.add_node("parse_task", parse_task)
    workflow.add_node("query_data", query_data)
    workflow.add_node("analyze_gis", analyze_gis)
    workflow.add_node("retrieve_knowledge", retrieve_knowledge)
    workflow.add_node("generate_report", generate_report)

    workflow.set_entry_point("parse_task")

    workflow.add_conditional_edges("parse_task", should_continue, {
        "query_data": "query_data",
        "end": END,
    })
    workflow.add_conditional_edges("query_data", should_continue, {
        "analyze_gis": "analyze_gis",
        "end": END,
    })
    workflow.add_conditional_edges("analyze_gis", should_continue, {
        "retrieve_knowledge": "retrieve_knowledge",
        "end": END,
    })
    workflow.add_conditional_edges("retrieve_knowledge", should_continue, {
        "generate_report": "generate_report",
        "end": END,
    })
    workflow.add_edge("generate_report", END)

    return workflow.compile()


# ===== 编排器对外接口 =====

class OrchestratorAgent:
    """任务编排 Agent（依赖 db session 构造真实节点）"""

    def __init__(self, db_session=None, user_id=None, is_admin=False):
        self.db = db_session
        self.user_id = user_id
        self.is_admin = is_admin
        nodes = _make_nodes(db_session, user_id=user_id, is_admin=is_admin) if db_session is not None else _make_fallback_nodes()
        self.graph = build_workflow_graph(nodes)

    async def execute(self, user_query: str) -> dict[str, Any]:
        """执行完整分析流程"""
        initial = AgentState(
            user_query=user_query,
            parsed_intent={},
            data_results={},
            gis_results={},
            knowledge_results=[],
            report="",
            status="pending",
            steps=[],
            error=None,
        )
        result = self.graph.invoke(initial)
        return {
            "report": result.get("report", ""),
            "steps": result.get("steps", []),
            "status": result.get("status", "failed"),
            "llm_used": llm_available(),
            "data": result.get("data_results", {}),
            "gis": result.get("gis_results", {}),
            "knowledge": result.get("knowledge_results", []),
        }


def _make_fallback_nodes():
    """无 db 时的兜底节点（保持图结构可用，返回占位数据）"""
    def parse_task(state: AgentState) -> dict:
        steps = state.get("steps", [])
        steps.append({"step": "parse_task", "agent": "Orchestrator", "input": state["user_query"],
                      "output": {"plan": [{"task_type": "query_data", "description": "默认计划"}]},
                      "status": "completed", "summary": "任务拆解完成（数据库未连接）"})
        return {"parsed_intent": {"plan": []}, "steps": steps, "status": "parsed"}

    def query_data(state: AgentState) -> dict:
        steps = state.get("steps", [])
        steps.append({"step": "query_data", "agent": "DataAgent", "input": state["user_query"],
                      "output": {"error": "数据库未连接"}, "status": "failed",
                      "summary": "DataAgent 无法查询（数据库未连接）"})
        return {"data_results": {"status": "no_db", "total": 0, "items": []}, "steps": steps, "status": "data_ready"}

    def analyze_gis(state: AgentState) -> dict:
        steps = state.get("steps", [])
        steps.append({"step": "analyze_gis", "agent": "GisAgent", "input": state["data_results"],
                      "output": {"hotspots": []}, "status": "completed", "summary": "GisAgent 无数据可分析"})
        return {"gis_results": {"status": "no_data", "hotspots": [], "summary": "无数据"}, "steps": steps, "status": "gis_ready"}

    def retrieve_knowledge(state: AgentState) -> dict:
        steps = state.get("steps", [])
        steps.append({"step": "retrieve_knowledge", "agent": "RagAgent", "input": state["user_query"],
                      "output": {"matched": 0}, "status": "completed", "summary": "RagAgent 无知识库可检索"})
        return {"knowledge_results": [], "steps": steps, "status": "knowledge_ready"}

    def generate_report(state: AgentState) -> dict:
        steps = state.get("steps", [])
        report = _template_report(state["user_query"], 0, 0, 0, "无", "无", "无") + settings.REPORT_FOOTER
        steps.append({"step": "generate_report", "agent": "ReportAgent", "input": state["user_query"],
                      "output": {"report_length": len(report)}, "status": "completed",
                      "summary": "ReportAgent 生成报告（无数据库）"})
        return {"report": report, "steps": steps, "status": "completed"}

    return parse_task, query_data, analyze_gis, retrieve_knowledge, generate_report
