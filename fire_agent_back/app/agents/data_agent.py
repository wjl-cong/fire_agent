"""
数据 Agent — 使用 LangChain 工具调用查询数据库
"""
from app.repositories.fire_repository import FireRepository


class DataAgent:
    """数据 Agent：查询 & 聚合火险数据"""

    def __init__(self, db_session=None):
        self.repo = FireRepository(db_session) if db_session else None

    async def query_fire_data(self, params: dict) -> dict:
        """查询火险数据"""
        if not self.repo:
            return {"error": "数据库未连接", "total": 0, "items": []}
        try:
            from app.schemas.dashboard import HistoryFireQuery
            q = HistoryFireQuery(
                start_date=params.get("start_date"),
                end_date=params.get("end_date"),
                city=params.get("city"),
            )
            return self.repo.query_history_fires(q)
        except Exception as e:
            return {"error": str(e), "total": 0, "items": []}

    async def aggregate_statistics(self, params: dict) -> dict:
        """聚合统计"""
        if not self.repo:
            return {"error": "数据库未连接"}
        try:
            return self.repo.get_summary(
                start_date=params.get("start_date"),
                end_date=params.get("end_date"),
            )
        except Exception as e:
            return {"error": str(e)}