"""
GIS 分析 Agent — 空间分析工具
"""
import json
import math

from app.services.query_service import CITY_CENTERS


def _nearest_city(lng: float, lat: float) -> str:
    """坐标 → 最近州市中心（经度距离按纬度余弦修正），为热点网格标注真实属地。

    必须由数据侧标注属地：LLM 仅凭经纬度会编造地名（如把普洱写成横断山区）。
    """
    best, best_d = None, float("inf")
    for name, (clng, clat) in CITY_CENTERS.items():
        d = ((lng - clng) * math.cos(math.radians(lat))) ** 2 + (lat - clat) ** 2
        if d < best_d:
            best, best_d = name, d
    return best or ""


class GisAgent:
    """GIS 分析 Agent：空间分析、热区识别"""

    async def analyze_hotspots(self, fire_data: dict, boundary: dict = None) -> dict:
        """识别高风险区域"""
        items = fire_data.get("items", [])
        if not items:
            return {"hotspots": [], "summary": "无数据"}

        # 简单风险区域识别：按经纬度网格聚类
        grid = {}
        for item in items:
            lng = item.get("longitude", 0)
            lat = item.get("latitude", 0)
            # 0.1度网格
            key = f"{round(lng, 1)},{round(lat, 1)}"
            if key not in grid:
                grid[key] = {"lng": round(lng, 1), "lat": round(lat, 1), "count": 0, "avg_frp": 0, "frp_sum": 0}
            grid[key]["count"] += 1
            grid[key]["frp_sum"] += item.get("frp", 0) or 0

        hotspots = []
        for key, g in grid.items():
            g["avg_frp"] = round(g["frp_sum"] / g["count"], 2) if g["count"] > 0 else 0
            if g["count"] >= 2:  # 至少2个火点才算热点
                g["city"] = _nearest_city(g["lng"], g["lat"])
                hotspots.append(g)

        hotspots.sort(key=lambda x: x["count"], reverse=True)
        return {
            "hotspots": hotspots[:20],
            "total_hotspots": len(hotspots),
            "summary": f"识别到 {len(hotspots)} 个热点区域",
        }

    async def analyze_predicted(self, fire_data: dict, top_n: int = 20) -> dict:
        """预测火险数据的热点识别：州市级预测点无空间密度，按火险等级识别高风险区域"""
        import math
        items = fire_data.get("items", [])
        if not items:
            return {"hotspots": [], "summary": "无数据"}

        hotspots = []
        for item in items:
            risk = item.get("risk_score") or 0
            # 火险等级：risk_score(0-1) → 1-5 级
            level = max(1, min(5, math.ceil(risk / 0.2) if risk > 0 else 1))
            if level < 3:  # 中风险以上才算热点区域
                continue
            hotspots.append({
                "lng": item.get("longitude", 0),
                "lat": item.get("latitude", 0),
                "city": item.get("city"),
                "count": int(round(item.get("frp") or 0)),
                "avg_frp": round(item.get("frp") or 0, 2),
                "risk_score": round(risk, 4),
                "level": level,
            })

        hotspots.sort(key=lambda x: x["risk_score"], reverse=True)
        return {
            "hotspots": hotspots[:top_n],
            "total_hotspots": len(hotspots),
            "summary": f"识别到 {len(hotspots)} 个高风险区域（中风险以上）",
        }

    async def buffer_analysis(self, center: tuple, radius: float = 0.1) -> dict:
        """缓冲区分析（简化版，后续可用 PostGIS ST_Buffer）"""
        lng, lat = center
        return {
            "center": {"lng": lng, "lat": lat},
            "radius": radius,
            "bounds": {
                "min_lng": lng - radius,
                "max_lng": lng + radius,
                "min_lat": lat - radius,
                "max_lat": lat + radius,
            },
            "summary": f"以 ({lng}, {lat}) 为中心，半径 {radius}° 的缓冲区",
        }