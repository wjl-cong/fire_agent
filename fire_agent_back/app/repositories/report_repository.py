"""
报告数据访问层 — 报告的增删改查
"""
from datetime import datetime

from sqlalchemy.orm import Session

from app.models.report import AnalysisReport
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
            llm_provider=req.llm_provider,
            llm_model=getattr(req, "llm_model", None),
            llm_tokens=req.llm_tokens,
            llm_degraded=bool(req.llm_degraded),
            created_at=now,
            updated_at=now,
        )
        self.db.add(report)
        self.db.commit()
        self.db.refresh(report)
        return report

    def list(self, page: int = 1, page_size: int = 20, report_type: str = None,
             user_id: int = None, is_admin: bool = False) -> dict:
        """分页查询报告列表（不含正文，省流量）

        可见性规则（软删除）：
        - 普通用户：仅自己的报告，且未被自己删除（hidden）、未被管理员删除（deleted）
        - 管理员：所有人的报告（含用户自删 hidden 的），但自己删除过（deleted）的除外
        """
        q = self.db.query(AnalysisReport).filter(AnalysisReport.deleted == False)  # noqa: E712
        if not is_admin:
            q = q.filter(AnalysisReport.user_id == user_id,
                         AnalysisReport.hidden == False)  # noqa: E712
        if report_type:
            q = q.filter(AnalysisReport.report_type == report_type)
        total = q.count()
        # 按 updated_at 倒序：Agent 重生成同标题报告走 upsert（只刷 updated_at、不动 created_at），
        # 若按 created_at 排序，重新生成的报告会沉底，用户会误以为「报告中心没有新报告」
        items = q.order_by(AnalysisReport.updated_at.desc()) \
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
                    "owner_hidden": bool(r.hidden),
                    "llm_provider": r.llm_provider,
                    "llm_model": r.llm_model,
                    "llm_degraded": bool(r.llm_degraded),
                    "created_at": r.created_at.strftime("%Y-%m-%d %H:%M:%S") if r.created_at else None,
                    "updated_at": r.updated_at.strftime("%Y-%m-%d %H:%M:%S") if r.updated_at else None,
                }
                for r in items
            ],
        }

    def get(self, report_id: int, user_id: int = None, is_admin: bool = False,
            include_deleted: bool = False) -> dict:
        """查询单条报告详情（仅本人或管理员可见）

        include_deleted=True 供 Agent 任务详情使用：即使报告在报告中心被删除，
        多 Agent 协作历史仍能查看报告内容（两个模块互不影响）。
        """
        r = self.db.query(AnalysisReport).filter(AnalysisReport.id == report_id).first()
        if not r:
            return None
        if not include_deleted:
            if r.deleted:
                return None
            if not is_admin and (r.user_id != user_id or r.hidden):
                return None
        elif not is_admin and r.user_id != user_id:
            return None
        return {
            "id": r.id,
            "title": r.title,
            "report_type": r.report_type,
            "summary": r.summary,
            "content": r.content,
            "tags": r.tags,
            "status": r.status,
            "llm_provider": r.llm_provider,
            "llm_model": r.llm_model,
            "llm_tokens": r.llm_tokens,
            "llm_degraded": bool(r.llm_degraded),
            "created_at": r.created_at.strftime("%Y-%m-%d %H:%M:%S") if r.created_at else None,
            "updated_at": r.updated_at.strftime("%Y-%m-%d %H:%M:%S") if r.updated_at else None,
        }

    def delete(self, report_id: int, user_id: int = None, is_admin: bool = False) -> bool:
        """删除报告（软删除，仅改标记，不动 Agent 任务引用）

        - 管理员删除：deleted=True → 所有人在报告中心都看不到
        - 普通用户删除自己的：hidden=True → 仅该用户在报告中心看不到，
          管理员仍可见（owner_hidden 标记）；多 Agent 任务详情不受影响
        """
        r = self.db.query(AnalysisReport).filter(AnalysisReport.id == report_id).first()
        if not r:
            return False
        if not is_admin and r.user_id != user_id:
            return False
        if is_admin:
            r.deleted = True
        else:
            r.hidden = True
        r.updated_at = datetime.now()
        self.db.commit()
        return True