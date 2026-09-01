"""
Agent 任务与步骤日志表
"""
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship

from app.core.database import Base


class AgentTask(Base):
    __tablename__ = "agent_tasks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True, comment="归属用户 ID")
    task_name = Column(String(200), comment="任务名称")
    task_type = Column(String(50), comment="任务类型")
    user_query = Column(Text, nullable=False, comment="用户原始输入")
    status = Column(String(20), default="pending", comment="状态 pending/running/completed/failed")
    current_step = Column(String(100), comment="当前步骤")
    final_summary = Column(Text, comment="最终结论摘要")
    report_id = Column(Integer, ForeignKey("analysis_reports.id"), nullable=True, comment="关联报告 ID")
    started_at = Column(DateTime, comment="开始时间")
    finished_at = Column(DateTime, comment="完成时间")
    created_at = Column(DateTime, comment="创建时间")

    steps = relationship("AgentTaskStep", back_populates="task", cascade="all, delete-orphan")


class AgentTaskStep(Base):
    __tablename__ = "agent_task_steps"

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(Integer, ForeignKey("agent_tasks.id"), nullable=False, comment="关联任务 ID")
    step_order = Column(Integer, comment="步骤序号")
    agent_name = Column(String(50), comment="执行 Agent 名称")
    step_name = Column(String(100), comment="步骤名称")
    input_payload = Column(JSON, comment="输入数据")
    output_payload = Column(JSON, comment="输出数据")
    status = Column(String(20), default="pending", comment="状态 pending/running/completed/failed")
    started_at = Column(DateTime, comment="开始时间")
    finished_at = Column(DateTime, comment="完成时间")

    task = relationship("AgentTask", back_populates="steps")