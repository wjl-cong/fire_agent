"""
RAG 知识库 Schema
"""
from pydantic import BaseModel


class RagAskRequest(BaseModel):
    """RAG 提问请求"""
    query: str
    top_k: int = 5


class RagAskResponse(BaseModel):
    """RAG 回答"""
    answer: str
    references: list[dict]
    llm_used: bool


class DocumentInfo(BaseModel):
    """文档信息"""
    id: int
    title: str
    category: str
    status: str
    summary: str | None
    created_at: str | None