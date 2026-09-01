"""
通用 Pydantic Schema
"""
from datetime import datetime
from pydantic import BaseModel


class ApiResponse(BaseModel):
    """统一 API 响应包装"""
    code: int = 200
    message: str = "success"
    data: object | None = None


class PaginationParams(BaseModel):
    """分页参数"""
    page: int = 1
    page_size: int = 20


class PaginatedResponse(BaseModel):
    """分页响应"""
    items: list
    total: int
    page: int
    page_size: int
    total_pages: int