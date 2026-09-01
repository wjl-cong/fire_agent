"""
数据库初始化 — 创建 PostGIS 扩展 + 表结构

用法:
  python scripts/init_db.py
  python scripts/init_db.py --drop  (先删表再重建)
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import text
from app.core.database import engine, Base

# 必须导入所有模型，否则 metadata 为空，create_all 不会创建任何表
from app.models import (  # noqa: F401
    HistoricalFirePoint,
    PredictedFireRisk,
    RegionBoundary,
    EmergencyResource,
    AgentTask,
    AgentTaskStep,
    AnalysisReport,
    KbDocument,
    KbChunk,
)


def init_database(drop_first: bool = False):
    """初始化数据库：启用 PostGIS + 创建表"""

    print("=" * 60)
    print("数据库初始化开始")
    print("=" * 60)

    # 连接数据库
    conn = engine.connect()

    # 1. 启用 PostGIS 扩展
    print("[1/3] 启用 PostGIS 扩展...")
    try:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
        conn.commit()
        print("  [OK] PostGIS 已就绪")
    except Exception as e:
        conn.rollback()
        print(f"  [ERROR] 启用 PostGIS 失败: {e}")
        conn.close()
        return

    # 2. 可选：删除已有表
    if drop_first:
        print("[2/3] 删除已有表...")
        try:
            Base.metadata.drop_all(bind=engine)
            print("  [OK] 表已删除")
        except Exception as e:
            print(f"  [WARN] 删除表失败（可能不存在）: {e}")

    # 3. 创建表
    step = "2/3" if drop_first else "2/3"
    print(f"[{step}] 创建数据库表...")
    try:
        Base.metadata.create_all(bind=engine)
        print("  [OK] 表已创建:")
        for table in Base.metadata.sorted_tables:
            print(f"    - {table.name}")
    except Exception as e:
        print(f"  [ERROR] 创建表失败: {e}")
        conn.close()
        return

    conn.close()
    print("=" * 60)
    print("数据库初始化完成")
    print("=" * 60)


if __name__ == "__main__":
    drop = "--drop" in sys.argv
    init_database(drop_first=drop)