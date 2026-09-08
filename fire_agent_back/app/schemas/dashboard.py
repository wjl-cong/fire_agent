"""
大屏数据接口 Schema
"""
from datetime import date
from pydantic import BaseModel


class HistoryFireQuery(BaseModel):
    """历史火点查询参数"""
    start_date: date | None = None
    end_date: date | None = None
    city: str | None = None
    confidence: str | None = None
    page: int = 1
    page_size: int = 500


class HistoryFirePoint(BaseModel):
    """历史火点输出"""
    id: int
    acq_date: date
    acq_time: str | None
    frp: float | None
    confidence: str | None
    conf: str | None
    longitude: float
    latitude: float
    city: str | None

    class Config:
        from_attributes = True


class PredictRiskQuery(BaseModel):
    """预测火险查询参数"""
    year: int | None = None
    month: int | None = None
    day: int | None = None
    view_mode: str = "daily"
    city: str | None = None


class PredictRiskPoint(BaseModel):
    """预测火险输出"""
    id: int
    city: str
    year: int
    month: int
    day: int | None
    view_mode: str
    base_fire_index: float | None
    final_fire_index: float | None
    fire_level: int | None
    pred_fire_count: float | None
    pred_fire_risk: float | None
    risk_score: float | None
    longitude: float | None
    latitude: float | None

    class Config:
        from_attributes = True


class DashboardSummary(BaseModel):
    """大屏摘要统计"""
    total_fire_points: int = 0
    high_risk_count: int = 0
    avg_frp: float = 0
    top_cities: list[dict] = []