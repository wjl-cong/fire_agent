"""
报告中心接口 — 报告列表 / 详情 / 生成 / 删除 / 导出

用户隔离：普通用户仅能访问/删除/导出自己的报告；管理员可见全部。
"""
from fastapi import APIRouter, Depends, Query, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.repositories.report_repository import ReportRepository
from app.schemas.report import ReportGenerateRequest

router = APIRouter()

# ====== Markdown → 完整 HTML 文档（含中文+内联样式，便于打印/存PDF） ======
_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8">
<title>{title}</title>
<style>
  body {{
    max-width: 840px;
    margin: 40px auto;
    padding: 0 24px;
    font-family: "Microsoft YaHei", "SimSun", sans-serif;
    font-size: 14px;
    line-height: 1.8;
    color: #1e293b;
  }}
  h1 {{ border-bottom: 2px solid #0ea5e9; padding-bottom: 8px; color: #0f172a; }}
  h2 {{ margin-top: 24px; color: #0f172a; }}
  h3 {{ color: #0f172a; }}
  blockquote {{ border-left: 4px solid #0ea5e9; margin: 12px 0; padding: 8px 16px; background: #f1f5f9; color: #475569; }}
  code {{ background: #f1f5f9; padding: 1px 5px; border-radius: 3px; }}
  a {{ color: #0ea5e9; text-decoration: none; }}
  a:hover {{ text-decoration: underline; }}
  table {{ border-collapse: collapse; width: 100%; }}
  th, td {{ border: 1px solid #cbd5e1; padding: 6px 10px; text-align: left; }}
  th {{ background: #f8fafc; }}
  @media print {{
    body {{ margin: 0; }}
    h1 {{ page-break-after: avoid; }}
  }}
</style>
</head>
<body>
{body}
</body>
</html>"""


@router.get("/list")
async def list_reports(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    report_type: str | None = Query(None),
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    """报告列表（普通用户仅自己的，管理员全部）"""
    repo = ReportRepository(db)
    result = repo.list(
        page=page,
        page_size=page_size,
        report_type=report_type,
        user_id=current.id,
        is_admin=current.role == "admin",
    )
    return {"code": 200, "message": "success", "data": result}


@router.get("/{report_id}")
async def get_report(
    report_id: int,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    """报告详情（仅本人或管理员）"""
    repo = ReportRepository(db)
    detail = repo.get(report_id, user_id=current.id, is_admin=current.role == "admin")
    if not detail:
        raise HTTPException(status_code=404, detail="报告不存在或无权限查看")
    return {"code": 200, "message": "success", "data": detail}


@router.post("/generate")
async def generate_report(
    req: ReportGenerateRequest,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    """生成（保存）报告（归属当前用户）"""
    repo = ReportRepository(db)
    report = repo.create(req, user_id=current.id)
    return {
        "code": 200,
        "message": "success",
        "data": {
            "id": report.id,
            "title": report.title,
            "status": report.status,
        },
    }


@router.delete("/{report_id}")
async def delete_report(
    report_id: int,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    """删除报告（仅本人或管理员）"""
    repo = ReportRepository(db)
    ok = repo.delete(report_id, user_id=current.id, is_admin=current.role == "admin")
    if not ok:
        raise HTTPException(status_code=404, detail="报告不存在或无权限删除")
    return {"code": 200, "message": "success", "data": {"id": report_id}}


@router.get("/export/{report_id}")
async def export_report(
    report_id: int,
    format: str = Query("html", pattern="^(html|md)$"),
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    """导出报告：format=html 供打印/存 PDF；format=md 返回 Markdown（仅本人或管理员）"""
    repo = ReportRepository(db)
    detail = repo.get(report_id, user_id=current.id, is_admin=current.role == "admin")
    if not detail:
        raise HTTPException(status_code=404, detail="报告不存在或无权限导出")
    content = detail.get("content") or ""
    title = detail.get("title") or "报告"

    if format == "md":
        filename = f"report_{report_id}.md"
        return Response(
            content=content,
            media_type="text/markdown; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    # format=html
    try:
        import markdown as md
        body = md.markdown(
            content,
            extensions=["extra", "sane_lists", "fenced_code"],
        )
    except Exception:
        body = content.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        body = body.replace("\n", "<br>\n")
    html = _HTML_TEMPLATE.format(title=title, body=body)
    filename = f"report_{report_id}.html"
    return Response(
        content=html,
        media_type="text/html; charset=utf-8",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )