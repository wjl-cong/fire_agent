"""
报告数据访问层 — 报告的增删改查
"""
from datetime import datetime

from sqlalchemy.orm import Session

from app.models.report import AnalysisReport
from app.models.task import AgentTask
from app.schemas.report import ReportGenerateRequest


class ReportRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, req: ReportGenerateRequest, user_id: int = None) -> AnalysisReport:
        """创建新报告"""
        now = datetime.now()
        report = AnalysisReport(
            user_id=user_id,
            title=req.title or "未命名报告",
            report_type=req.report_type,
            summary=req.summary,
            content=req.content,
            tags=req.tags,
            status="published",
            created_at=now,
            updated_at=now,
        )
        self.db.add(report)
        self.db.commit()
        self.db.refresh(report)
        return report

    def list(self, page: int = 1, page_size: int = 20, report_type: str = None,
             user_id: int = None, is_admin: bool = False) -> dict:
        """分页查询报告列表（不含正文，省流量）— 普通用户仅自己的，管理员全部

        注意：普通用户严格只看到 user_id == 当前用户 的报告，
        不再包含旧版无归属（NULL）记录，避免普通用户互相看到对方的历史报告。
        """
        q = self.db.query(AnalysisReport)
        if not is_admin:
            q = q.filter(AnalysisReport.user_id == user_id)
        if report_type:
            q = q.filter(AnalysisReport.report_type == report_type)
        total = q.count()
        items = q.order_by(AnalysisReport.created_at.desc()) \
                 .offset((page - 1) * page_size) \
                 .limit(page_size) \
                 .all()
        return {
            "total": total,
            "page": page,
            "page_size": page_size,
            "items": [
                {
                    "id": r.id,
                    "title": r.title,
                    "report_type": r.report_type,
                    "summary": r.summary,
                    "tags": r.tags,
                    "status": r.status,
                    "created_at": r.created_at.strftime("%Y-%m-%d %H:%M:%S") if r.created_at else None,
                }
                for r in items
            ],
        }

    def get(self, report_id: int, user_id: int = None, is_admin: bool = False) -> dict:
        """查询单条报告详情（仅本人或管理员可见）"""
        r = self.db.query(AnalysisReport).filter(AnalysisReport.id == report_id).first()
        if not r:
            return None
        if not is_admin and r.user_id != user_id:
            return None
        return {
            "id": r.id,
            "title": r.title,
            "report_type": r.report_type,
            "summary": r.summary,
            "content": r.content,
            "tags": r.tags,
            "status": r.status,
            "created_at": r.created_at.strftime("%Y-%m-%d %H:%M:%S") if r.created_at else None,
        }

    def delete(self, report_id: int, user_id: int = None, is_admin: bool = False) -> bool:
        """删除报告（仅本人或管理员）"""
        r = self.db.query(AnalysisReport).filter(AnalysisReport.id == report_id).first()
        if not r:
            return False
        if not is_admin and r.user_id != user_id:
            return False
        self.db.delete(r)
        self.db.commit()
        return True

    def upsert_from_task(self, title: str, content: str, summary: str = None,
                         report_type: str = "special", tags: list = None,
                         user_id: int = None) -> AnalysisReport:
        """将 Agent 分析结果落库为报告，按「标题 + 归属用户」去重

        注意：仅在同一用户范围内按标题去重，绝不占用/覆盖其他用户或旧版
        无归属（NULL）报告，避免不同用户互相覆盖、串看内容。
        """
        q = self.db.query(AnalysisReport).filter(AnalysisReport.title == title)
        if user_id is not None:
            q = q.filter(AnalysisReport.user_id == user_id)
        existing = q.first()
        now = datetime.now()
        if existing:
            existing.content = content
            existing.summary = summary or existing.summary
            existing.report_type = report_type
            if tags:
                existing.tags = tags
            existing.updated_at = now
            self.db.commit()
            self.db.refresh(existing)
            return existing
        return self.create(
            ReportGenerateRequest(
                title=title,
                report_type=report_type,
                summary=summary,
                content=content,
                tags=tags,
            ),
            user_id=user_id,
        )