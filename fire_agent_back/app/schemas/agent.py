"""
Agent Schema
"""
from typing import Literal

from pydantic import BaseModel


class AgentTaskRequest(BaseModel):
    """Agent 任务请求"""
    query: str


class TaskResumeRequest(BaseModel):
    """HITL 审批决策请求（POST /tasks/{id}/resume）"""
    action: Literal["approve", "edit", "reject"]
    content: str = ""  # action=edit 时的新报告内容
    comment: str = ""  # action=reject 时的驳回意见


class AgentTaskResult(BaseModel):
    """Agent 任务结果"""
    report: str
    steps: list[dict]
    status: str
    llm_used: bool