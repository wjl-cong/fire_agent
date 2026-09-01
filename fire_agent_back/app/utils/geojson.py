"""
GeoJSON 工具函数
"""


def feature_collection(features: list[dict]) -> dict:
    """包装为 FeatureCollection"""
    return {
        "type": "FeatureCollection",
        "features": features,
    }


def point_feature(lng: float, lat: float, properties: dict = None) -> dict:
    """创建点要素"""
    return {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [lng, lat]},
        "properties": properties or {},
    }