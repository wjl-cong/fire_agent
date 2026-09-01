"""
智能查询接口 — 自然语言查询 / 结构化查询执行 / 查询历史

用户隔离：查询历史严格按 user_id 归属；管理员可见全部。
"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.models.query_history import QueryHistory
from app.schemas.query import QueryRequest
from app.services.query_service import QueryService

router = APIRouter()


def _save_history(db: Session, user_id: int, text: str, summary: str, method: str, payload: dict):
    """保存查询历史（同用户同文本去重；存储完整结果供点击历史直接回显）"""
    row = db.query(QueryHistory).filter(
        QueryHistory.user_id == user_id,
        QueryHistory.query_text == text,
    ).first()
    if row:
        row.summary = summary
        row.method = method
        row.result = payload
        row.created_at = datetime.now()
    else:
        db.add(QueryHistory(user_id=user_id, query_text=text, summary=summary,
                            method=method, result=payload))
    db.commit()


@router.post("/parse", response_model=dict)
async def parse_query(req: QueryRequest, db: Session = Depends(get_db)):
    """解析自然语言查询，返回结构化参数"""
    svc = QueryService(db)
    parsed = svc.parse(req.query)
    return {
        "code": 200,
        "message": "success",
        "data": parsed.model_dump(),
    }


@router.post("/execute", response_model=dict)
async def execute_query(
    req: QueryRequest,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    """执行自然语言查询，返回结果并自动保存查询历史（归属当前用户）"""
    svc = QueryService(db)
    parsed = svc.parse(req.query)
    result = svc.execute(parsed)

    # 成功后落库（同文本去重，存储完整结果供历史回显）
    payload = {
        "query": req.query,
        "parsed": parsed.model_dump(),
        "result": result.model_dump(),
    }
    try:
        _save_history(db, current.id, req.query, result.summary, parsed.method, payload)
    except Exception:
        db.rollback()

    return {
        "code": 200,
        "message": "success",
        "data": payload,
    }


@router.get("/history")
async def list_history(
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    """查询历史列表（普通用户仅自己的，管理员全部）"""
    q = db.query(QueryHistory)
    if current.role != "admin":
        q = q.filter(QueryHistory.user_id == current.id)
    rows = q.order_by(QueryHistory.created_at.desc()).limit(50).all()
    return {
        "code": 200,
        "message": "success",
        "data": [
            {
                "id": r.id,
                "text": r.query_text,
                "summary": r.summary or "",
                "method": r.method or "keyword",
                "time": r.created_at.strftime("%Y-%m-%d %H:%M:%S") if r.created_at else "",
            }
            for r in rows
        ],
    }


@router.get("/history/{history_id}")
async def get_history_detail(
    history_id: int,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    """获取单条历史记录的完整存储结果（点击历史直接回显，不重新查询）"""
    r = db.query(QueryHistory).filter(QueryHistory.id == history_id).first()
    if not r or (current.role != "admin" and r.user_id != current.id):
        raise HTTPException(status_code=404, detail="记录不存在或无权限访问")
    return {
        "code": 200,
        "message": "success",
        "data": {
            "id": r.id,
            "text": r.query_text,
            "summary": r.summary or "",
            "method": r.method or "keyword",
            "time": r.created_at.strftime("%Y-%m-%d %H:%M:%S") if r.created_at else "",
            "result": r.result,
        },
    }


@router.delete("/history")
async def clear_history(
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    """清空当前用户的查询历史"""
    q = db.query(QueryHistory)
    if current.role != "admin":
        q = q.filter(QueryHistory.user_id == current.id)
    q.delete(synchronize_session=False)
    db.commit()
    return {"code": 200, "message": "success", "data": {"cleared": True}}


@router.delete("/history/{history_id}")
async def delete_history(
    history_id: int,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    """删除单条查询历史（仅本人或管理员）"""
    r = db.query(QueryHistory).filter(QueryHistory.id == history_id).first()
    if not r or (current.role != "admin" and r.user_id != current.id):
        raise HTTPException(status_code=404, detail="记录不存在或无权限删除")
    db.delete(r)
    db.commit()
    return {"code": 200, "message": "success", "data": {"id": history_id}}
