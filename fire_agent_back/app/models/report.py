"""
分析报告表
"""
from sqlalchemy import Column, Integer, String, Text, DateTime, JSON, ForeignKey, Boolean

from app.core.database import Base


class AnalysisReport(Base):
    __tablename__ = "analysis_reports"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True, comment="归属用户 ID")
    title = Column(String(200), comment="报告标题")
    report_type = Column(String(50), comment="报告类型 daily/weekly/monthly/special")
    summary = Column(Text, comment="报告摘要")
    content = Column(Text, comment="报告正文 (Markdown)")
    sections = Column(JSON, comment="结构化章节")
    tags = Column(JSON, comment="标签列表")
    status = Column(String(20), default="draft", comment="状态 draft/published/archived")
    # 软删除：用户删除仅自己不可见（hidden）；管理员删除全局不可见（deleted）
    hidden = Column(Boolean, default=False, server_default="false", comment="用户自删标记（仅本人不可见，admin 仍可见）")
    deleted = Column(Boolean, default=False, server_default="false", comment="管理员删除标记（全局不可见）")
    # LLM 审计元数据：Agent 生成时记录实际 Provider / token 用量 / 是否降级（模板兜底时留空）
    llm_provider = Column(String(50), comment="生成该报告的 LLM Provider（模板兜底为空）")
    llm_model = Column(String(120), comment="生成该报告的 LLM 模型名（如 qwen-max，模板兜底为空）")
    llm_tokens = Column(JSON, comment="LLM token 用量 {prompt_tokens, completion_tokens, total_tokens}")
    llm_degraded = Column(Boolean, default=False, server_default="false", comment="是否降级产出（重试/熔断/换 Provider）")
    created_at = Column(DateTime, comment="创建时间")
    updated_at = Column(DateTime, comment="更新时间")