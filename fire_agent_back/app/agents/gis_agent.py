"""
GIS 分析 Agent — 空间分析工具
"""
import json


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
                hotspots.append(g)

        hotspots.sort(key=lambda x: x["count"], reverse=True)
        return {
            "hotspots": hotspots[:20],
            "total_hotspots": len(hotspots),
            "summary": f"识别到 {len(hotspots)} 个热点区域",
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