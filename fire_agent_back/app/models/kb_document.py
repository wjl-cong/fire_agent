"""
知识库文档与分片表
"""
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship

from app.core.database import Base


class KbDocument(Base):
    __tablename__ = "kb_documents"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True, comment="上传用户 ID")
    title = Column(String(200), nullable=False, comment="文档标题")
    category = Column(String(50), comment="分类 policy/regulation/manual/other")
    source_path = Column(String(500), comment="原始文件路径")
    file_type = Column(String(20), comment="文件类型 pdf/txt/md/docx")
    status = Column(String(20), default="pending", comment="状态 pending/processing/ready/failed")
    summary = Column(Text, comment="文档摘要")
    created_at = Column(DateTime, comment="创建时间")

    chunks = relationship("KbChunk", back_populates="document", cascade="all, delete-orphan")


class KbChunk(Base):
    __tablename__ = "kb_chunks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    document_id = Column(Integer, ForeignKey("kb_documents.id"), nullable=False, comment="关联文档 ID")
    chunk_index = Column(Integer, comment="分片序号")
    content = Column(Text, nullable=False, comment="分片文本内容")
    token_count = Column(Integer, comment="Token 数量")
    # embedding 字段用 pgvector 的 VECTOR 类型，需另行安装 pgvector 扩展
    # 此处先用 Text 占位，后续升级
    embedding = Column(Text, nullable=True, comment="向量化结果 (JSON 序列化)")
    created_at = Column(DateTime, comment="创建时间")

    document = relationship("KbDocument", back_populates="chunks")