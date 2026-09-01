"""
视觉识别历史模型 — AI 火情识别记录持久化
"""
from sqlalchemy import Column, Integer, String, Text, DateTime, func

from app.core.database import Base


class VisionHistory(Base):
    __tablename__ = "vision_history"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True, nullable=False)          # 归属用户
    filename = Column(String(255))                                  # 原始文件名
    image_path = Column(String(512))                                # 图片存储路径
    analysis = Column(Text)                                         # 识别结果（Markdown）
    model = Column(String(64))                                      # 使用的视觉模型
    created_at = Column(DateTime(timezone=True), server_default=func.now())
