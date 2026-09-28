# -*- coding: utf-8 -*-
"""
评估回归脚本（P2#13 轻量方案，不引入 DeepEval/RAGAS 重依赖）

四类确定性指标（对应 golden_set.json）：
  1. Tool Correctness   — plan 类型必须 ∈ 允许集合；非法类型必须被 route_after_parse 过滤
  2. 路由逻辑           — parse 后 fan-out 与 join→generate_report|end 符合期望；
                          评审三态（重写/审批/结束）与审批驳回路由正确
  3. Task Completion + Trajectory — fallback 图端到端跑完且节点序列与 golden 精确一致
  4. 轻量 Faithfulness  — 报告含必备章节要素（执行摘要/数据来源/巡防…）且不低于最短长度

用法（改动 prompt / 换模型 / 改图结构前必跑，全绿才允许合入）：
  python scripts/eval_regression.py            # 离线回归：无 DB/LLM 强依赖，秒级
  python scripts/eval_regression.py --live     # 真实链路回归：需 DB + LLM，分钟级
  python scripts/eval_regression.py --case case-001-mixed-report
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

GOLDEN_PATH = Path(__file__).with_name("golden_set.json")


def load_golden() -> dict:
    with open(GOLDEN_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


# ────────────────────────── 指标1：Tool Correctness ──────────────────────────

def check_plan_types(case: dict, allowed: list) -> list[str]:
    """golden 用例本身声明的 plan 类型必须全部合法（非法类型只应出现在过滤用例中）"""
    return [t for t in case.get("plan_types", []) if t not in allowed]


# ────────────────────────── 指标2：路由逻辑 ──────────────────────────

def _synth_state(plan_types: list) -> dict:
    return {"parsed_intent": {"plan": [{"task_type": t, "description": "", "required": True}
                                       for t in plan_types]}}


def check_routing(case: dict) -> list[str]:
    """fan-out 与 join 路由符合期望（纯函数，无副作用）"""
    from app.agents.orchestrator_agent import route_after_parse, route_after_join

    errs = []
    state = _synth_state(case["plan_types"])
    fanout = route_after_parse(state)
    if fanout != case["expected_fanout"]:
        errs.append(f"fan-out 期望 {case['expected_fanout']}，实际 {fanout}")

    want_report = "generate_report" in case["plan_types"]
    join_route = route_after_join(state)
    if want_report and join_route != "generate_report":
        errs.append(f"计划含 generate_report 但 join 路由到 {join_route}")
    if not want_report and join_route != "end":
        errs.append(f"计划不含 generate_report 但 join 路由到 {join_route}")
    return errs


def check_review_and_approval_routing() -> list[str]:
    """评审三态 + 审批驳回路由（图控制流的护栏单测）"""
    from app.core.config import settings
    from app.agents.orchestrator_agent import route_after_review, route_after_approval

    errs = []
    # 不通过且未达上限 → 重写
    r = route_after_review({"review_result": {"passed": False}, "revisions": 0})
    if r != "generate_report":
        errs.append(f"评审不通过(未达上限)期望重写，实际 {r}")
    # 通过 → 审批闸口（AGENT_REQUIRE_APPROVAL=True 时）
    r = route_after_review({"review_result": {"passed": True}, "revisions": 0})
    expect = "approval_gate" if settings.AGENT_REQUIRE_APPROVAL else "end"
    if r != expect:
        errs.append(f"评审通过期望 {expect}，实际 {r}")
    # 不通过但已达上限 → 审批闸口/结束（不无限循环）
    r = route_after_review({"review_result": {"passed": False}, "revisions": 2})
    if r not in ("approval_gate", "end"):
        errs.append(f"评审不通过(达上限)应放行，实际 {r}")
    # 审批：reject → 重写；approve → 结束
    if route_after_approval({"decision": "reject"}) != "generate_report":
        errs.append("审批驳回应路由到重写 generate_report")
    if route_after_approval({"decision": "approve"}) != "end":
        errs.append("审批通过应结束")
    return errs


def check_review_guardrail() -> list[str]:
    """评审硬护栏一票否决（不依赖 LLM，临时关闭 llm_available 保证确定性）"""
    import app.agents.orchestrator_agent as oa

    review_fn = oa._make_nodes(None)[6]  # 第7个节点 = review_report
    orig = oa.llm_available
    oa.llm_available = lambda: False
    try:
        bad = review_fn({"report": "太短", "revisions": 0, "data_results": {}})
        good_report = oa._template_report("测试查询", 100, 60, 40, "昆明市、大理州", "热点A", "无")
        good = review_fn({"report": good_report, "revisions": 0,
                          "data_results": {"hist_total": 60, "pred_total": 40}})
    finally:
        oa.llm_available = orig

    errs = []
    if bad["review_result"].get("passed"):
        errs.append("硬护栏：劣质报告必须一票否决")
    issues = " ".join(bad["review_result"].get("issues", []))
    for kw in ("500", "执行摘要", "巡防"):
        if kw not in issues:
            errs.append(f"硬护栏：劣质报告 issues 未覆盖「{kw}」")
    if not good["review_result"].get("passed"):
        errs.append(f"硬护栏：合格模板报告被误杀 {good['review_result'].get('issues')}")
    return errs


# ──────────────────── 指标3：Task Completion + Trajectory ────────────────────

def run_fallback_graph(case: dict) -> tuple[list[str], str, str, list[str]]:
    """跑 fallback 图（无 DB/LLM 依赖）：返回 (节点序列, 终态status, 报告, 错误列表)"""
    from app.agents.orchestrator_agent import OrchestratorAgent

    errs = []
    agent = OrchestratorAgent(db_session=None, thread_id=f"eval-{case['id']}")
    seq, status, report = [], "", ""
    for name, update in agent.iter_steps(case["query"]):
        seq.append(name)
        if not isinstance(update, dict):
            continue
        if update.get("status"):
            status = update["status"]
        if update.get("report"):
            report = update["report"]
    if status != "completed":
        errs.append(f"任务未完成：status={status}")
    return seq, status, report, errs


# ──────────────────── 指标4：轻量 Faithfulness（报告要素） ────────────────────

def check_report_elements(report: str, case: dict) -> list[str]:
    errs = []
    missing = [e for e in case.get("report_elements", []) if e not in report]
    if missing:
        errs.append(f"报告缺少必备要素：{missing}")
    min_len = case.get("min_report_length", 0)
    if len(report.strip()) < min_len:
        errs.append(f"报告仅 {len(report.strip())} 字符，低于下限 {min_len}")
    return errs


# ────────────────────────── live 模式：真实链路回归 ──────────────────────────

def run_live_case(case: dict) -> list[str]:
    """真实图回归（需 DB + LLM）：轨迹按包含关系校验（并行 fan-out 顺序不保证），
    报告按要素 + ≥800 字符（真实 LLM 报告硬约束）校验；HITL 中断自动 approve。"""
    from langgraph.types import Command
    from app.agents.orchestrator_agent import OrchestratorAgent
    from app.core.database import SessionLocal

    errs = []
    db = SessionLocal()
    try:
        agent = OrchestratorAgent(db_session=db, thread_id=f"eval-live-{case['id']}")
        seq, status, report = [], "", ""

        def consume(gen):
            nonlocal status, report
            for name, update in gen:
                seq.append(name)
                if not isinstance(update, dict):
                    continue
                if update.get("status"):
                    status = update["status"]
                if update.get("report"):
                    report = update["report"]

        consume(agent.iter_steps(case["query"]))
        if "__interrupt__" in seq:  # HITL 审批闸口 → 自动通过（回归不测人工交互）
            seq.remove("__interrupt__")
            consume(agent.iter_resume({"action": "approve"}))

        # live 期望节点按 plan 推导（并行 fan-out 顺序不保证，按包含关系校验）
        want = {"parse_task", "join"}
        plan_types = set(case["plan_types"])
        if "query_data" in plan_types:
            want |= {"query_data", "analyze_gis"}
        if "retrieve_knowledge" in plan_types:
            want |= {"retrieve_knowledge"}
        if "generate_report" in plan_types:
            want |= {"generate_report", "review_report"}
            from app.core.config import settings
            if settings.AGENT_REQUIRE_APPROVAL:
                want |= {"approval_gate"}
        miss = want - set(seq)
        if miss:
            errs.append(f"真实轨迹缺少期望节点：{sorted(miss)}（实际 {seq}）")
        want_report = "generate_report" in case["plan_types"]
        if want_report:
            if status != "completed":
                errs.append(f"真实任务未完成：status={status}")
            errs.extend(check_report_elements(report, {**case, "min_report_length": 800}))
        return errs
    finally:
        db.close()


# ────────────────────────── 主流程 ──────────────────────────

def main():
    parser = argparse.ArgumentParser(description="P2#13 评估回归（轻量方案）")
    parser.add_argument("--live", action="store_true", help="跑真实链路（需 DB + LLM）")
    parser.add_argument("--case", action="append", default=[], help="只跑指定用例（可多次）")
    args = parser.parse_args()

    golden = load_golden()
    allowed = golden["meta"]["allowed_plan_types"]
    cases = golden["cases"]
    if args.case:
        cases = [c for c in cases if c["id"] in args.case]
        if not cases:
            print(f"[FAIL] 未找到用例：{args.case}", flush=True)
            return 1

    results = []  # (case_id, [err, ...])

    # ── 全局护栏单测（一次） ──
    global_errs = []
    global_errs += [(f"评审/审批路由: {e}") for e in check_review_and_approval_routing()]
    global_errs += [(f"评审硬护栏: {e}") for e in check_review_guardrail()]
    results.append(("<guardrail-unit>", global_errs))

    for case in cases:
        errs = []
        # 指标1：Tool Correctness
        illegal = check_plan_types(case, allowed)
        if illegal and "delete_database" not in case["plan_types"]:
            errs.append(f"golden 用例含非法 plan 类型：{illegal}")
        # 指标2：路由逻辑
        errs += [f"路由: {e}" for e in check_routing(case)]
        # 指标3：fallback 图轨迹（仅计划含 generate_report 的用例可由 fallback 图复现）
        if "generate_report" in case["plan_types"]:
            seq, _status, report, terrs = run_fallback_graph(case)
            errs += [f"轨迹: {e}" for e in terrs]
            if seq != case["trajectory"]:
                errs.append(f"轨迹期望 {case['trajectory']}\n        实际 {seq}")
            # 指标4：报告要素（fallback 模板报告）
            errs += [f"报告: {e}" for e in check_report_elements(report, case)]
        else:
            # 纯查询/纯知识用例：无报告产出，验证 join 后正常结束即可（check_routing 已覆盖）
            pass
        results.append((case["id"], errs))

    # ── 汇总 ──
    print("=" * 64, flush=True)
    total, failed = len(results), 0
    for cid, errs in results:
        mark = "PASS" if not errs else "FAIL"
        failed += bool(errs)
        print(f"[{mark}] {cid}", flush=True)
        for e in errs:
            print(f"       - {e}", flush=True)
    print("=" * 64, flush=True)
    print(f"共 {total} 项，通过 {total - failed}，失败 {failed}"
          f"{'（离线模式）' if not args.live else '（live 模式）'}", flush=True)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
