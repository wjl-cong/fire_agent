"""
RAG Agent — 使用 LangChain 做知识库检索增强问答
"""
from app.core.llm import get_llm, get_embedding, llm_available
from app.services.rag_service import RagService


class RagAgent:
    """RAG Agent：检索知识库文档，结合上下文回答问题"""

    def __init__(self, rag_service: RagService = None):
        self.rag = rag_service
        self.llm = get_llm()
        self.embed = get_embedding()

    async def retrieve(self, query: str, top_k: int = 5, user_id: int = None, is_admin: bool = False) -> dict:
        """检索相关文档片段（返回含检索过程元数据的 dict）"""
        if not self.rag:
            return {
                "items": [{"content": "RAG 服务未初始化", "score": 0}],
                "total_chunks": 0, "matched_chunks": 0, "method": "none",
                "keywords": [], "vector_enabled": False,
            }
        return self.rag.retrieve(query, top_k, user_id=user_id, is_admin=is_admin)

    async def answer(self, query: str, context: dict = None) -> dict:
        """基于检索结果生成回答"""
        if not self.rag:
            return {"answer": "RAG 服务未初始化", "references": [], "llm_used": False}
        retrieved = await self.retrieve(query) if context is None else context
        return self.rag.answer(query, retrieved)