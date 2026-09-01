"""
智能查询 Schema
"""
from datetime import date
from pydantic import BaseModel


class QueryRequest(BaseModel):
    """查询请求"""
    query: str  # 用户自然语言输入


class QueryParseResult(BaseModel):
    """解析结果"""
    intent: str  # history / predict / summary
    params: dict  # 解析出的结构化参数
    explanation: str  # 解析说明
    method: str = "keyword"  # llm / keyword：标识解析方式


class QueryResult(BaseModel):
    """查询结果"""
    summary: str  # 文字摘要
    table_data: list[dict] = []  # 表格数据
    chart_data: dict | None = None  # 图表数据
    chart_type: str | None = None  # bar / line / pie
    geo_data: dict | None = None  # 地图数据 GeoJSON
    total: int = 0