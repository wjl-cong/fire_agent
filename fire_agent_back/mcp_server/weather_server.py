"""
MCP Server — 高德天气只读数据源（P2#14）

独立进程，stdio 传输：python -m mcp_server.weather_server
边界（与升级方案一致）：仅封装只读数据源；数据库访问仍走仓储层，不开放 text-to-SQL。
依赖：pip install mcp httpx
"""
import os

import httpx
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("fire-weather")

AMAP_GEO = "https://restapi.amap.com/v3/geocode/geo"
AMAP_WEATHER = "https://restapi.amap.com/v3/weather/weatherInfo"


def _key() -> str:
    return os.environ.get("AMAP_KEY", "")


@mcp.tool()
def get_weather(city: str) -> dict:
    """查询中国城市实时天气（高德数据源）。

    Args:
        city: 城市名，如「昆明市」「玉溪市」
    Returns:
        {ok, city, weather, temperature, wind_direction, wind_power, humidity, report_time}
    """
    key = _key()
    if not key:
        return {"ok": False, "error": "服务端未配置 AMAP_KEY"}
    try:
        geo = httpx.get(AMAP_GEO, params={"address": city, "key": key}, timeout=8).json()
        adcode = ((geo.get("geocodes") or [{}])[0].get("adcode"))
        if not adcode:
            return {"ok": False, "error": f"无法解析城市：{city}"}
        wx = httpx.get(AMAP_WEATHER, params={"city": adcode, "key": key, "extensions": "base"},
                       timeout=8).json()
        lives = wx.get("lives") or []
        if not lives:
            return {"ok": False, "error": f"无天气数据：{city}"}
        live = lives[0]
        return {
            "ok": True,
            "city": live.get("city"),
            "weather": live.get("weather"),
            "temperature": live.get("temperature"),
            "wind_direction": live.get("winddirection"),
            "wind_power": live.get("windpower"),
            "humidity": live.get("humidity"),
            "report_time": live.get("reporttime"),
        }
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


if __name__ == "__main__":
    mcp.run()  # stdio 传输
