"""
应急资源表 — 消防站点、水源点、物资点等
"""
from sqlalchemy import Column, Integer, String, Float
from geoalchemy2 import Geometry

from app.core.database import Base


class EmergencyResource(Base):
    __tablename__ = "emergency_resources"

    id = Column(Integer, primary_key=True, autoincrement=True)
    resource_name = Column(String(200), nullable=False, comment="资源名称")
    resource_type = Column(String(50), comment="资源类型 station/water/material/other")
    resource_level = Column(String(20), comment="资源等级")
    city = Column(String(50), index=True, comment="所属城市")
    address = Column(String(300), comment="详细地址")
    longitude = Column(Float, comment="经度")
    latitude = Column(Float, comment="纬度")
    geom = Column(Geometry("POINT", srid=4326), comment="空间几何字段")
    contact_person = Column(String(50), comment="联系人")
    contact_phone = Column(String(20), comment="联系电话")
    status = Column(String(20), default="active", comment="状态 active/inactive")