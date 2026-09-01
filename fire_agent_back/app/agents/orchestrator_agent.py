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

    # ---------- 节点2：数据查询（真实调用 DataAgent） ----------
    def query_data(state: AgentState) -> dict:
        from app.schemas.dashboard import HistoryFireQuery
        steps = state.get("steps", [])
        query = state["user_query"]
        data = {"status": "no_data", "total": 0, "items": []}
        try:
            # 抽取年份/城市（简化：从任务描述中解析，含年份则查询历史火点）
            import re
            year_m = re.search(r"(20\d{2})", query)
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
            q = HistoryFireQuery(
                start_date=f"{year_m.group(1)}-01-01" if year_m else None,
                end_date=f"{year_m.group(1)}-12-31" if year_m else None,
                city=city,
            )
            data = fire_repo.query_history_fires(q)
            data["status"] = "queried"
        except Exception as e:
            data = {"status": "error", "total": 0, "items": [], "error": str(e)}

        steps.append({"step": "query_data", "agent": "DataAgent", "input": query,
                      "output": {"total": data.get("total", 0), "first_city": (data.get("items") or [{}])[0].get("city") if data.get("items") else None},
                      "status": "completed",
                      "summary": f"DataAgent 查询到 {data.get('total', 0)} 条历史火点"})
        return {"data_results": data, "steps": steps, "status": "data_ready"}

    # ---------- 节点3：GIS 分析（真实调用 GisAgent） ----------
    def analyze_gis(state: AgentState) -> dict:
        steps = state.get("steps", [])
        gis = {"status": "no_data", "hotspots": [], "summary": "无数据"}
        try:
            gis = asyncio_run(gis_agent.analyze_hotspots(state.get("data_results", {})))
            gis["status"] = "analyzed"
        except Exception as e:
            gis = {"status": "error", "hotspots": [], "summary": str(e)}

        steps.append({"step": "analyze_gis", "agent": "GisAgent",
                      "input": f"对 {state.get('data_results', {}).get('total', 0)} 条火点做网格聚类",
                      "output": {"hotspots": gis.get("hotspots", [])[:5],
                                 "total_hotspots": gis.get("total_hotspots", 0)},
                      "status": "completed",
                      "summary": f"GisAgent 识别到 {gis.get('total_hotspots', 0)} 个热点区域"})
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
        items = data.get("items", []) or []
        top_cities = {}
        for it in items:
            c = it.get("city")
            if c:
                top_cities[c] = top_cities.get(c, 0) + 1
        top_cities_str = ", ".join(f"{c}({n})" for c, n in sorted(top_cities.items(), key=lambda x: -x[1])[:5]) or "无"

        hotspots = gis.get("hotspots", []) or []
        hotspot_str = "; ".join(
            f"[{h.get('lng', 0):.2f},{h.get('lat', 0):.2f}] 火点{h.get('count', 0)}个/平均FRP{h.get('avg_frp', 0)}"
            for h in hotspots[:5]
        ) or "无"

        kb_str = "\n".join(
            f"- （{k.get('document', '未知')}，相关度{k.get('score', 0)}）{k.get('content', '')[:100]}"
            for k in knowledge[:3]
        ) or "无"

        if llm_available():
            llm = get_llm(temperature=0.3)
            prompt = f"""你是一个森林火险分析报告生成助手（ReportAgent）。请根据以下真实数据生成专业的分析报告。

用户需求：{query}

## 真实数据（DataAgent 查询结果）
- 历史火点总数：{data_total} 条
- 火点分布（Top 城市）：{top_cities_str}

## GIS 热点分析（GisAgent 分析结果）
- 热点区域：{hotspot_str}

## 知识库参考（RagAgent 检索结果）
{ kb_str }

请生成一份 Markdown 格式的报告，必须基于以上真实数据，包含：
1. 概述
2. 数据分析结果（引用上面的真实数字）
3. 风险区域识别（引用热点区域）
4. 处置建议
5. 参考依据（引用知识库片段）"""
            try:
                resp = llm.invoke(prompt)
                report = resp.content if hasattr(resp, "content") else str(resp)
            except Exception as e:
                report = _template_report(query, data_total, top_cities_str, hotspot_str, kb_str) + f"\n\n> LLM 调用异常：{e}"
        else:
            report = _template_report(query, data_total, top_cities_str, hotspot_str, kb_str)

        steps.append({"step": "generate_report", "agent": "ReportAgent", "input": query,
                      "output": {"report_length": len(report)}, "status": "completed",
                      "summary": f"ReportAgent 生成 {len(report)} 字符报告"})
        # 统一追加系统署名（开发者信息 + 项目地址）
        report = report + settings.REPORT_FOOTER
        return {"report": report, "steps": steps, "status": "completed"}

    return parse_task, query_data, analyze_gis, retrieve_knowledge, generate_report


def _template_report(query, data_total, top_cities, hotspot, kb) -> str:
    """无 LLM 时的模板报告（仍含真实数据）"""
    return f"""# 火险分析报告

## 概述
基于用户查询「{query}」的多 Agent 协作分析结果。

## 数据分析结果（DataAgent）
- 历史火点总数：{data_total} 条
- 火点分布（Top 城市）：{top_cities}

## 风险区域识别（GisAgent）
- 热点区域：{hotspot}

## 参考依据（RagAgent）
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
        report = _template_report(state["user_query"], 0, "无", "无", "无") + settings.REPORT_FOOTER
        steps.append({"step": "generate_report", "agent": "ReportAgent", "input": state["user_query"],
                      "output": {"report_length": len(report)}, "status": "completed",
                      "summary": "ReportAgent 生成报告（无数据库）"})
        return {"report": report, "steps": steps, "status": "completed"}

    return parse_task, query_data, analyze_gis, retrieve_knowledge, generate_report
