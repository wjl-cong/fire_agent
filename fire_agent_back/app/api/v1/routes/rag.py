"""
RAG 知识库接口 — 文档管理 & 检索问答 & 问答历史

用户隔离：普通用户仅能访问/检索/删除自己的文档与历史；管理员可见全部。
"""
import os
from datetime import datetime

from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.models.rag_history import RagHistory
from app.services.rag_service import RagService
from app.schemas.rag import RagAskRequest

router = APIRouter()


def _save_history(db: Session, user_id: int, query: str, result: dict):
    """保存问答历史（同用户同问题去重；存储完整结果供点击历史直接回显）"""
    row = db.query(RagHistory).filter(
        RagHistory.user_id == user_id,
        RagHistory.query_text == query,
    ).first()
    retrieval = result.get("retrieval") or {}
    fields = dict(
        answer=result.get("answer") or "",
        method=retrieval.get("method") or "none",
        llm_used=1 if result.get("llm_used") else 0,
        matched=retrieval.get("matched_chunks") or 0,
        result=result,
    )
    if row:
        for k, v in fields.items():
            setattr(row, k, v)
        row.created_at = datetime.now()
    else:
        db.add(RagHistory(user_id=user_id, query_text=query, **fields))
    db.commit()


@router.post("/ask")
async def rag_ask(
    req: RagAskRequest,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    """RAG 问答（仅检索当前用户可见的文档），自动保存问答历史"""
    svc = RagService(db)
    result = svc.retrieve(req.query, req.top_k, user_id=current.id, is_admin=current.role == "admin")
    result = svc.answer(req.query, result)
    try:
        _save_history(db, current.id, req.query, result)
    except Exception:
        db.rollback()
    return {
        "code": 200,
        "message": "success",
        "data": result,
    }


@router.get("/history")
async def list_history(
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    """问答历史列表（普通用户仅自己的，管理员全部）"""
    q = db.query(RagHistory)
    if current.role != "admin":
        q = q.filter(RagHistory.user_id == current.id)
    rows = q.order_by(RagHistory.created_at.desc()).limit(50).all()
    return {
        "code": 200,
        "message": "success",
        "data": [
            {
                "id": r.id,
                "text": r.query_text,
                "answer": (r.answer or "")[:200],
                "method": r.method or "none",
                "llm_used": bool(r.llm_used),
                "matched": r.matched or 0,
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
    """获取单条问答历史的完整存储结果（点击历史直接回显，不重新检索）"""
    r = db.query(RagHistory).filter(RagHistory.id == history_id).first()
    if not r or (current.role != "admin" and r.user_id != current.id):
        raise HTTPException(status_code=404, detail="记录不存在或无权限访问")
    return {
        "code": 200,
        "message": "success",
        "data": {
            "id": r.id,
            "text": r.query_text,
            "time": r.created_at.strftime("%Y-%m-%d %H:%M:%S") if r.created_at else "",
            "result": r.result,
        },
    }


@router.delete("/history")
async def clear_history(
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    """清空当前用户的问答历史"""
    q = db.query(RagHistory)
    if current.role != "admin":
        q = q.filter(RagHistory.user_id == current.id)
    q.delete(synchronize_session=False)
    db.commit()
    return {"code": 200, "message": "success", "data": {"cleared": True}}


@router.delete("/history/{history_id}")
async def delete_history(
    history_id: int,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    """删除单条问答历史（仅本人或管理员）"""
    r = db.query(RagHistory).filter(RagHistory.id == history_id).first()
    if not r or (current.role != "admin" and r.user_id != current.id):
        raise HTTPException(status_code=404, detail="记录不存在或无权限删除")
    db.delete(r)
    db.commit()
    return {"code": 200, "message": "success", "data": {"id": history_id}}


@router.post("/documents")
async def upload_document(
    file: UploadFile = File(...),
    category: str = Form("other"),
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    """上传知识库文档（归属当前用户）"""
    svc = RagService(db)
    content = await file.read()
    result = svc.upload_document(content, file.filename, category, user_id=current.id)
    return {
        "code": 200,
        "message": "success",
        "data": result,
    }


@router.get("/documents")
async def list_documents(
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    """文档列表（普通用户仅自己的，管理员全部）"""
    svc = RagService(db)
    docs = svc.list_documents(user_id=current.id, is_admin=current.role == "admin")
    return {
        "code": 200,
        "message": "success",
        "data": docs,
    }


@router.delete("/documents/{doc_id}")
async def delete_document(
    doc_id: int,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    """删除文档（仅本人或管理员）"""
    svc = RagService(db)
    ok = svc.delete_document(doc_id, user_id=current.id, is_admin=current.role == "admin")
    if not ok:
        raise HTTPException(status_code=404, detail="文档不存在或无权限删除")
    return {
        "code": 200,
        "message": "deleted",
    }
