"""
Agent Schema
"""
from pydantic import BaseModel


class AgentTaskRequest(BaseModel):
    """Agent 任务请求"""
    query: str


class AgentTaskResult(BaseModel):
    """Agent 任务结果"""
    report: str
    steps: list[dict]
    status: str
    llm_used: bool