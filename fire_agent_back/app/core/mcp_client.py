"""
MCP 客户端接入（P2#14）— langchain-mcp-adapters 加载本地 MCP server 工具

- 边界：仅接入只读数据源 server（高德天气）；数据库仍走仓储层，不开放 text-to-SQL
- 降级：MCP_ENABLED=False 或 mcp / langchain-mcp-adapters 未安装时返回空，调用方静默跳过
- 工具定义进程内缓存一次；stdio 子进程的拉起/退出由 adapters 管理
"""
import json
import os
import sys
from pathlib import Path

from app.core.config import settings

_tools_cache = None
_tools_failed = False

# 工作目录 = 项目根（mcp_server 包所在），子进程继承 AMAP_KEY 等环境变量
_SERVER_CWD = str(Path(__file__).resolve().parents[2])
_SERVER_ENV = {**os.environ}


def get_mcp_tools() -> list:
    """加载 MCP server 工具（同步阻塞；在 worker 线程内调用，无事件循环冲突）"""
    global _tools_cache, _tools_failed
    if not settings.MCP_ENABLED or _tools_failed:
        return []
    if _tools_cache is not None:
        return _tools_cache
    try:
        import asyncio
        from langchain_mcp_adapters.client import MultiServerMCPClient

        client = MultiServerMCPClient({
            "fire_weather": {
                "command": sys.executable,
                "args": ["-m", "mcp_server.weather_server"],
                "env": _SERVER_ENV,
                "cwd": _SERVER_CWD,
                "transport": "stdio",
            },
        })
        tools = asyncio.run(client.get_tools())
        _tools_cache = list(tools or [])
        return _tools_cache
    except Exception:
        _tools_failed = True
        return []


def get_weather_for_city(city: str) -> str:
    """调用 MCP get_weather 工具，返回一句话天气描述；任何失败返回空串（不阻断主流程）"""
    tools = get_mcp_tools()
    tool = next((t for t in tools if getattr(t, "name", "") == "get_weather"), None)
    if tool is None or not city:
        return ""
    try:
        import asyncio
        raw = asyncio.run(tool.ainvoke({"city": city}))
        data = raw if isinstance(raw, dict) else json.loads(str(raw))
        if not data.get("ok"):
            return ""
        return (f"{data.get('city', city)} {data.get('weather')} {data.get('temperature')}℃ "
                f"风{data.get('wind_direction')}{data.get('wind_power')}级 "
                f"湿度{data.get('humidity')}%")
    except Exception:
        return ""
