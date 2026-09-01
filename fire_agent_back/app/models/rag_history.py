"""
知识库问答历史表 — 按用户隔离，同一用户同一问题只保留一条（重问不产生重复）
"""
from datetime import datetime

from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, JSON

from app.core.database import Base


class RagHistory(Base):
    __tablename__ = "rag_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True, comment="归属用户 ID")
    query_text = Column(Text, nullable=False, comment="提问原文")
    answer = Column(Text, comment="回答内容")
    method = Column(String(20), comment="检索方式 hybrid/vector/keyword/none")
    llm_used = Column(Integer, default=0, comment="是否使用 LLM 增强 0/1")
    matched = Column(Integer, default=0, comment="命中片段数")
    result = Column(JSON, comment="完整问答结果（点击历史直接回显，不再重新检索）")
    created_at = Column(DateTime, default=datetime.now, comment="提问时间")
