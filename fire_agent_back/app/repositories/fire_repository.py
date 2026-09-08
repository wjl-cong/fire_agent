"""
火险数据访问层 — 历史火点 & 预测火险
"""
from datetime import datetime
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.fire_point import HistoricalFirePoint
from app.models.fire_risk import PredictedFireRisk
from app.schemas.dashboard import HistoryFireQuery, PredictRiskQuery, DashboardSummary


class FireRepository:
    def __init__(self, db: Session):
        self.db = db

    def query_history_fires(self, query: HistoryFireQuery) -> dict:
        """查询历史火点"""
        q = self.db.query(HistoricalFirePoint)

        if query.start_date:
            q = q.filter(HistoricalFirePoint.acq_date >= query.start_date)
        if query.end_date:
            q = q.filter(HistoricalFirePoint.acq_date <= query.end_date)
        if query.city:
            q = q.filter(HistoricalFirePoint.city == query.city)
        if query.confidence:
            q = q.filter(HistoricalFirePoint.conf == query.confidence)

        total = q.count()
        items = q.order_by(HistoricalFirePoint.acq_date.desc())\
                 .offset((query.page - 1) * query.page_size)\
                 .limit(query.page_size)\
                 .all()

        return {
            "total": total,
            "page": query.page,
            "page_size": query.page_size,
            "items": [
                {
                    "id": p.id,
                    "acq_date": str(p.acq_date),
                    "acq_time": p.acq_time,
                    "frp": p.frp,
                    "confidence": p.confidence,
                    "conf": p.conf,
                    "longitude": p.longitude,
                    "latitude": p.latitude,
                    "city": p.city,
                }
                for p in items
            ],
        }

    def query_predict_risks(self, query: PredictRiskQuery) -> dict:
        """查询预测火险"""
        q = self.db.query(PredictedFireRisk)

        if query.year:
            q = q.filter(PredictedFireRisk.year == query.year)
        if query.month:
            q = q.filter(PredictedFireRisk.month == query.month)
        if query.day is not None:
            q = q.filter(PredictedFireRisk.day == query.day)
        if query.view_mode:
            q = q.filter(PredictedFireRisk.view_mode == query.view_mode)
        if query.city:
            q = q.filter(PredictedFireRisk.city == query.city)

        items = q.order_by(PredictedFireRisk.city).all()

        return {
            "total": len(items),
            "items": [
                {
                    "id": r.id,
                    "city": r.city,
                    "year": r.year,
                    "month": r.month,
                    "day": r.day,
                    "view_mode": r.view_mode,
                    "base_fire_index": r.base_fire_index,
                    "final_fire_index": r.final_fire_index,
                    "fire_level": r.fire_level,
                    "pred_fire_count": r.pred_fire_count,
                    "pred_fire_risk": r.pred_fire_risk,
                    "risk_score": r.risk_score,
                    "longitude": r.longitude,
                    "latitude": r.latitude,
                }
                for r in items
            ],
        }

    def get_summary(self, start_date: str | None, end_date: str | None) -> dict:
        """获取大屏摘要统计"""
        q = self.db.query(HistoricalFirePoint)

        if start_date:
            q = q.filter(HistoricalFirePoint.acq_date >= start_date)
        if end_date:
            q = q.filter(HistoricalFirePoint.acq_date <= end_date)

        total = q.count()
        high_risk = q.filter(HistoricalFirePoint.conf == "high").count()
        avg_frp = q.with_entities(func.avg(HistoricalFirePoint.frp)).scalar() or 0

        # Top 5 高火点城市
        top_cities = (
            self.db.query(HistoricalFirePoint.city, func.count().label("cnt"))
            .filter(HistoricalFirePoint.city.isnot(None))
            .group_by(HistoricalFirePoint.city)
            .order_by(func.count().desc())
            .limit(5)
            .all()
        )

        return {
            "total_fire_points": total,
            "high_risk_count": high_risk,
            "avg_frp": round(float(avg_frp), 2),
            "top_cities": [{"city": c, "count": n} for c, n in top_cities],
        }

    def sample_fire_points(self, limit: int = 500) -> list[dict]:
        """取样本火点坐标，用于汇总类查询的地图展示（城市字段为空时兜底）"""
        pts = (
            self.db.query(
                HistoricalFirePoint.longitude,
                HistoricalFirePoint.latitude,
                HistoricalFirePoint.frp,
                HistoricalFirePoint.conf,
            )
            .filter(
                HistoricalFirePoint.longitude.isnot(None),
                HistoricalFirePoint.latitude.isnot(None),
            )
            .order_by(HistoricalFirePoint.acq_date.desc())
            .limit(limit)
            .all()
        )
        return [
            {
                "longitude": p.longitude,
                "latitude": p.latitude,
                "frp": p.frp,
                "confidence": p.conf,
            }
            for p in pts
        ]