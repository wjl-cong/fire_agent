"""
导入历史火点数据 — 从前端 Yunnan_fire.json (GeoJSON) 导入到 historical_fire_points 表

用法:
  python scripts/import_fire_points.py

数据来源: fire_agent_front/src/assets/Yunnan_fire.json
"""
import json
import sys
import os
from datetime import datetime, date

# 确保能导入 app 包
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.core.database import SessionLocal, engine, Base
from app.models.fire_point import HistoricalFirePoint
from geoalchemy2 import WKTElement


def import_fire_points(json_path: str) -> None:
    """导入历史火点 GeoJSON 数据"""

    if not os.path.exists(json_path):
        print(f"[ERROR] 文件不存在: {json_path}")
        return

    print(f"[INFO] 读取数据文件: {json_path}")
    with open(json_path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    features = raw.get("features", [])
    print(f"[INFO] 共 {len(features)} 条火点记录")

    # 获取数据库会话
    db = SessionLocal()
    try:
        count = 0
        batch = []

        for feat in features:
            props = feat.get("properties", {})
            geom = feat.get("geometry", {})

            if geom.get("type") != "Point":
                continue

            coords = geom.get("coordinates", [0, 0])
            lng, lat = coords[0], coords[1]

            acq_date_str = props.get("acq_date", "")
            try:
                acq_date = datetime.strptime(acq_date_str, "%Y-%m-%d").date() if acq_date_str else None
            except ValueError:
                acq_date = None

            frp = props.get("frp")
            if frp is not None:
                frp = float(frp)

            brightness = props.get("brightness")
            if brightness is not None:
                brightness = float(brightness)

            bright_t31 = props.get("bright_t31")
            if bright_t31 is not None:
                bright_t31 = float(bright_t31)

            confidence = props.get("confidence")
            if confidence is not None:
                confidence = str(confidence)

            conf = props.get("conf", "")

            record = HistoricalFirePoint(
                acq_date=acq_date,
                acq_time=props.get("acq_time", ""),
                daynight=props.get("daynight", ""),
                brightness=brightness,
                bright_t31=bright_t31,
                frp=frp,
                confidence=confidence,
                conf=conf,
                longitude=lng,
                latitude=lat,
                geom=WKTElement(f"POINT({lng} {lat})", srid=4326),
                province="云南省",
                city="",  # 可由后续空间关联填充
                source_type="MODIS",
                created_at=datetime.now(),
            )
            batch.append(record)
            count += 1

            # 每 500 条批量提交一次
            if len(batch) >= 500:
                db.add_all(batch)
                db.commit()
                print(f"[INFO] 已提交 {count}/{len(features)} 条")
                batch = []

        # 提交剩余批次
        if batch:
            db.add_all(batch)
            db.commit()

        print(f"[SUCCESS] 共导入 {count} 条历史火点记录")

    except Exception as e:
        db.rollback()
        print(f"[ERROR] 导入失败: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    # 默认路径：相对于项目根目录的 frontend JSON
    default_path = os.path.join(
        os.path.dirname(__file__),
        "..", "..", "fire_agent_front", "src", "assets", "Yunnan_fire.json"
    )
    path = sys.argv[1] if len(sys.argv) > 1 else default_path
    import_fire_points(path)