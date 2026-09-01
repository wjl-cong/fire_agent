"""
用户表
"""
from datetime import datetime

from sqlalchemy import Column, Integer, String, DateTime

from app.core.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(50), unique=True, nullable=False, index=True, comment="用户名")
    email = Column(String(120), unique=True, nullable=True, comment="邮箱")
    password_hash = Column(String(200), nullable=False, comment="密码哈希 (bcrypt)")
    role = Column(String(20), default="user", comment="角色 user/admin")
    created_at = Column(DateTime, default=datetime.now, comment="创建时间")