"""
多 Agent 工作流编排 — 使用 LangGraph
"""
from app.agents.orchestrator_agent import OrchestratorAgent


class AnalysisWorkflow:
    """标准分析工作流"""

    def __init__(self):
        self.orchestrator = OrchestratorAgent()

    async def run(self, user_query: str) -> dict:
        """执行完整分析流程"""
        return await self.orchestrator.execute(user_query)