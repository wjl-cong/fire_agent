"""
历史火点表 — 对应 NASA FIRMS MODIS 火点数据
"""
from sqlalchemy import Column, Integer, Float, String, DateTime, Date
from geoalchemy2 import Geometry

from app.core.database import Base


class HistoricalFirePoint(Base):
    __tablename__ = "historical_fire_points"

    id = Column(Integer, primary_key=True, autoincrement=True)
    acq_date = Column(Date, nullable=False, index=True, comment="火点采集日期")
    acq_time = Column(String(8), comment="火点采集时间")
    daynight = Column(String(4), comment="昼夜标记 D/N")
    brightness = Column(Float, comment="亮度温度 (K)")
    bright_t31 = Column(Float, comment="通道 31 亮度温度 (K)")
    frp = Column(Float, comment="火辐射功率 (MW)")
    confidence = Column(String(20), comment="置信度文字")
    conf = Column(String(20), comment="置信度等级 low/nominal/high")
    longitude = Column(Float, nullable=False, comment="经度")
    latitude = Column(Float, nullable=False, comment="纬度")
    geom = Column(Geometry("POINT", srid=4326), comment="空间几何字段")
    province = Column(String(50), comment="省")
    city = Column(String(50), index=True, comment="州市")
    source_type = Column(String(20), default="MODIS", comment="数据来源")
    created_at = Column(DateTime, comment="记录创建时间")