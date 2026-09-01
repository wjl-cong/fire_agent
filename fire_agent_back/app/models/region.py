"""
行政区边界表 — 州市/县区边界
"""
from sqlalchemy import Column, Integer, String
from geoalchemy2 import Geometry

from app.core.database import Base


class RegionBoundary(Base):
    __tablename__ = "region_boundaries"

    id = Column(Integer, primary_key=True, autoincrement=True)
    region_name = Column(String(100), nullable=False, comment="行政区名称")
    region_level = Column(String(10), comment="行政区级别 city/district")
    parent_region = Column(String(100), comment="上级行政区")
    region_code = Column(String(20), comment="行政区代码")
    geom = Column(Geometry("MULTIPOLYGON", srid=4326), comment="边界几何")
    center_lng = Column(String(20), comment="中心经度")
    center_lat = Column(String(20), comment="中心纬度")