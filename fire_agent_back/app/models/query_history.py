"""
智能查询历史表 — 按用户隔离，同一用户同一查询文本只保留一条（点击历史重查不产生重复）
"""
from datetime import datetime

from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, JSON

from app.core.database import Base


class QueryHistory(Base):
    __tablename__ = "query_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True, comment="归属用户 ID")
    query_text = Column(Text, nullable=False, comment="查询原文")
    summary = Column(Text, comment="结果摘要")
    method = Column(String(20), comment="解析方式 llm/keyword")
    result = Column(JSON, comment="完整查询结果（点击历史直接回显，不再重新查询）")
    created_at = Column(DateTime, default=datetime.now, comment="查询时间")
