"""
大屏数据接口 — 历史火点 / 预测火险 / 资源图层
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.repositories.fire_repository import FireRepository
from app.schemas.dashboard import (
    HistoryFireQuery,
    PredictRiskQuery,
    DashboardSummary,
)

router = APIRouter()


@router.get("/history-fires")
async def get_history_fires(
    start_date: str | None = Query(None, description="开始日期 YYYY-MM-DD"),
    end_date: str | None = Query(None, description="结束日期 YYYY-MM-DD"),
    city: str | None = Query(None, description="州市名称"),
    confidence: str | None = Query(None, description="置信度"),
    page: int = Query(1, ge=1),
    page_size: int = Query(500, ge=1, le=5000),
    db: Session = Depends(get_db),
):
    """查询历史火点数据"""
    repo = FireRepository(db)
    query = HistoryFireQuery(
        start_date=start_date,
        end_date=end_date,
        city=city,
        confidence=confidence,
        page=page,
        page_size=page_size,
    )
    result = repo.query_history_fires(query)
    return {
        "code": 200,
        "message": "success",
        "data": result,
    }


@router.get("/predict-risks")
async def get_predict_risks(
    year: int | None = Query(None, ge=2025, le=2026),
    month: int | None = Query(None, ge=1, le=12),
    day: int | None = Query(None, ge=1, le=31),
    view_mode: str = Query("daily", regex="^(daily|monthly)$"),
    city: str | None = Query(None),
    db: Session = Depends(get_db),
):
    """查询预测火险数据"""
    repo = FireRepository(db)
    query = PredictRiskQuery(
        year=year,
        month=month,
        day=day,
        view_mode=view_mode,
        city=city,
    )
    result = repo.query_predict_risks(query)
    return {
        "code": 200,
        "message": "success",
        "data": result,
    }


@router.get("/summary")
async def get_dashboard_summary(
    start_date: str | None = Query(None),
    end_date: str | None = Query(None),
    db: Session = Depends(get_db),
):
    """获取大屏摘要统计"""
    repo = FireRepository(db)
    summary = repo.get_summary(start_date, end_date)
    return {
        "code": 200,
        "message": "success",
        "data": summary,
    }