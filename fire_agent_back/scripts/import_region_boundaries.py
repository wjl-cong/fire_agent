"""
导入行政区边界数据 — 从前端 Yunnan_border.json (GeoJSON) 导入到 region_boundaries 表

用法:
  python scripts/import_region_boundaries.py
"""
import json
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.core.database import SessionLocal
from app.models.region import RegionBoundary
from geoalchemy2 import WKTElement
from shapely.geometry import shape, MultiPolygon, Polygon


def to_multipolygon_wkt(geom_dict: dict) -> str:
    """将 GeoJSON geometry 转为 MultiPolygon WKT"""
    g = shape(geom_dict)
    if isinstance(g, Polygon):
        g = MultiPolygon([g])
    return g.wkt


def compute_centroid(geom_dict: dict) -> tuple:
    """计算中心点坐标"""
    g = shape(geom_dict)
    if isinstance(g, Polygon):
        g = MultiPolygon([g])
    centroid = g.centroid
    return (round(centroid.x, 6), round(centroid.y, 6))


def import_region_boundaries(json_path: str) -> None:
    """导入行政区边界 GeoJSON 数据"""

    if not os.path.exists(json_path):
        print(f"[ERROR] 文件不存在: {json_path}")
        return

    print(f"[INFO] 读取数据文件: {json_path}")
    with open(json_path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    features = raw.get("features", [])
    print(f"[INFO] 共 {len(features)} 个行政区")

    db = SessionLocal()
    try:
        count = 0
        batch = []

        for feat in features:
            props = feat.get("properties", {})
            geom_dict = feat.get("geometry", {})

            name = props.get("name", "")
            gb_code = props.get("gb", "")

            if not name:
                continue

            # 计算 WKT 和中心点
            wkt = to_multipolygon_wkt(geom_dict)
            center_lng, center_lat = compute_centroid(geom_dict)

            record = RegionBoundary(
                region_name=name,
                region_level="city",
                parent_region="云南省",
                region_code=gb_code,
                geom=WKTElement(wkt, srid=4326),
                center_lng=str(center_lng),
                center_lat=str(center_lat),
            )
            batch.append(record)
            count += 1

        # 批量提交
        db.add_all(batch)
        db.commit()
        print(f"[SUCCESS] 共导入 {count} 个行政区边界")

        # 打印城市列表
        print("\n[INFO] 已导入城市:")
        for r in batch:
            print(f"  - {r.region_name} ({r.center_lng}, {r.center_lat})")

    except Exception as e:
        db.rollback()
        print(f"[ERROR] 导入失败: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    default_path = os.path.join(
        os.path.dirname(__file__),
        "..", "..", "fire_agent_front", "src", "assets", "Yunnan_border.json"
    )
    path = sys.argv[1] if len(sys.argv) > 1 else default_path
    import_region_boundaries(path)