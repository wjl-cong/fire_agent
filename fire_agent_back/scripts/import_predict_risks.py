"""
导入预测火险数据 — 从前端 predict_2025_2026_daily.json 和 predict_2025_2026_month.json 导入

用法:
  python scripts/import_predict_risks.py
  python scripts/import_predict_risks.py --daily <path> --monthly <path>
"""
import json
import sys
import os
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.core.database import SessionLocal
from app.models.fire_risk import PredictedFireRisk


def import_daily(json_path: str, db) -> int:
    """导入逐日预测数据"""
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    count = 0
    batch = []

    for item in data:
        record = PredictedFireRisk(
            city=item["City"],
            year=int(item["Year"]),
            month=int(item["Month"]),
            day=int(item["Day"]),
            view_mode="daily",
            base_fire_index=float(item.get("Base_Fire_Index", 0)),
            final_fire_index=float(item.get("Final_Fire_Index", 0)),
            fire_level=int(item.get("Fire_Level", 0)),
            pred_fire_count=float(item.get("Pred_Fire_Count", 0)),
            pred_fire_risk=None,
            risk_score=None,
            longitude=None,
            latitude=None,
            created_at=datetime.now(),
        )
        batch.append(record)
        count += 1

        if len(batch) >= 500:
            db.add_all(batch)
            db.commit()
            batch = []

    if batch:
        db.add_all(batch)
        db.commit()

    return count


def import_monthly(json_path: str, db) -> int:
    """导入逐月预测数据"""
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    count = 0
    batch = []

    for item in data:
        record = PredictedFireRisk(
            city=item["City"],
            year=int(item["Year"]),
            month=int(item["Month"]),
            day=None,
            view_mode="monthly",
            base_fire_index=None,
            final_fire_index=None,
            fire_level=None,
            pred_fire_count=None,
            pred_fire_risk=float(item.get("Pred_Fire_Risk", 0)),
            risk_score=float(item.get("Risk_Score", 0)),
            longitude=None,
            latitude=None,
            created_at=datetime.now(),
        )
        batch.append(record)
        count += 1

        if len(batch) >= 500:
            db.add_all(batch)
            db.commit()
            batch = []

    if batch:
        db.add_all(batch)
        db.commit()

    return count


def resolve_path(relative: str) -> str:
    """从项目根目录解析路径"""
    return os.path.join(os.path.dirname(__file__), "..", "..", relative)


def main():
    # 解析参数
    daily_path = None
    monthly_path = None
    args = sys.argv[1:]
    i = 0
    while i < len(args):
        if args[i] == "--daily" and i + 1 < len(args):
            daily_path = args[i + 1]
            i += 2
        elif args[i] == "--monthly" and i + 1 < len(args):
            monthly_path = args[i + 1]
            i += 2
        else:
            i += 1

    # 默认路径
    daily_path = daily_path or resolve_path(
        "fire_agent_front/src/assets/predict_2025_2026_daily.json"
    )
    monthly_path = monthly_path or resolve_path(
        "fire_agent_front/src/assets/predict_2025_2026_month.json"
    )

    if not os.path.exists(daily_path):
        print(f"[ERROR] 逐日文件不存在: {daily_path}")
        return
    if not os.path.exists(monthly_path):
        print(f"[ERROR] 逐月文件不存在: {monthly_path}")
        return

    db = SessionLocal()
    try:
        print(f"[INFO] 导入逐日数据: {daily_path}")
        daily_count = import_daily(daily_path, db)
        print(f"[INFO] 逐日数据导入完成: {daily_count} 条")

        print(f"[INFO] 导入逐月数据: {monthly_path}")
        monthly_count = import_monthly(monthly_path, db)
        print(f"[INFO] 逐月数据导入完成: {monthly_count} 条")

        print(f"[SUCCESS] 共导入 {daily_count + monthly_count} 条预测火险记录")

    except Exception as e:
        db.rollback()
        print(f"[ERROR] 导入失败: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()