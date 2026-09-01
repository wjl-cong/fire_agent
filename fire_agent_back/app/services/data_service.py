"""
数据查询服务 — 封装业务逻辑
"""
from app.repositories.fire_repository import FireRepository
from app.schemas.dashboard import HistoryFireQuery, PredictRiskQuery, DashboardSummary


class DataService:
    def __init__(self, db_session):
        self.repo = FireRepository(db_session)

    def get_history_fires(self, query: HistoryFireQuery) -> dict:
        return self.repo.query_history_fires(query)

    def get_predict_risks(self, query: PredictRiskQuery) -> dict:
        return self.repo.query_predict_risks(query)

    def get_dashboard_summary(self, start_date: str, end_date: str) -> dict:
        return self.repo.get_summary(start_date, end_date)