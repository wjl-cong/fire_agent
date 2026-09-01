"""
预测火险表 — 逐日/逐月预测数据
"""
from sqlalchemy import Column, Integer, Float, String, DateTime, Date
from geoalchemy2 import Geometry

from app.core.database import Base


class PredictedFireRisk(Base):
    __tablename__ = "predicted_fire_risks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    city = Column(String(50), nullable=False, index=True, comment="城市")
    year = Column(Integer, nullable=False, comment="年份")
    month = Column(Integer, nullable=False, comment="月份")
    day = Column(Integer, nullable=True, comment="日（逐日时非空，逐月时为 NULL）")
    view_mode = Column(String(10), nullable=False, comment="视图模式 daily/monthly")
    base_fire_index = Column(Float, comment="基础火险指数")
    final_fire_index = Column(Float, comment="最终火险指数")
    fire_level = Column(Integer, comment="火险等级 1-5")
    pred_fire_count = Column(Float, comment="预测火点数量")
    pred_fire_risk = Column(Float, comment="预测火险值")
    risk_score = Column(Float, comment="火险评分")
    longitude = Column(Float, comment="经度")
    latitude = Column(Float, comment="纬度")
    geom = Column(Geometry("POINT", srid=4326), comment="空间几何字段")
    created_at = Column(DateTime, comment="记录创建时间")