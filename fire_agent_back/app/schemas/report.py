"""
报告中心 Schema — 报告 DTO
"""
from typing import Optional
from pydantic import BaseModel


class ReportGenerateRequest(BaseModel):
    """报告生成请求"""
    title: Optional[str] = None
    report_type: str = "special"
    summary: Optional[str] = None
    content: str = ""
    tags: Optional[list[str]] = None
    overwrite: bool = False


class ReportOut(BaseModel):
    """报告输出 DTO"""
    id: int
    title: Optional[str] = None
    report_type: Optional[str] = None
    summary: Optional[str] = None
    content: Optional[str] = None
    tags: Optional[list] = None
    status: Optional[str] = None
    created_at: Optional[str] = None


class ReportBriefOut(BaseModel):
    """报告列表项（不含正文）"""
    id: int
    title: Optional[str] = None
    report_type: Optional[str] = None
    summary: Optional[str] = None
    tags: Optional[list] = None
    status: Optional[str] = None
    created_at: Optional[str] = None