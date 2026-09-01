"""
视觉与语音 API — 火情图像识别 / 语音识别 / 语音合成 / 识别历史

模型恒定使用阿里百炼（VISION_MODEL / ASR_MODEL / TTS_MODEL），
不受 ACTIVE_LLM_PROVIDER 切换影响。
"""
import base64
import os
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from langchain_core.messages import HumanMessage
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.llm import (
    get_vision_llm, transcribe_audio, synthesize_speech, vision_available,
)
from app.core.security import get_current_user
from app.models.user import User
from app.models.vision import VisionHistory

router = APIRouter()

# 视觉识别图片保存目录
VISION_UPLOAD_DIR = os.path.join("data", "vision_uploads")

# 火情识别系统提示词
FIRE_VISION_PROMPT = """你是森林火灾监测专家。请仔细分析这张图片，从专业角度输出：

1. **火情判定**：是否存在明火、烟雾或过火痕迹（判定为"明火/烟雾/无异常"）
2. **场景描述**：图片中的地形、植被、火势范围等关键信息
3. **严重程度**：按轻微/中等/严重/危急四级评估，并说明依据
4. **处置建议**：给出 2-3 条具体可行的应急建议

如果图片与火灾无关，请直接说明图片内容并注明"非火情场景"。"""


class SpeechRequest(BaseModel):
    """语音合成请求"""
    text: str


# ====== 视觉：火情图像识别 ======

@router.post("/analyze")
async def analyze_image(
    file: UploadFile = File(...),
    question: str = "",
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    上传图片进行火情识别分析（视觉模型 qwen-vl 系列）

    - file: 图片文件（jpg/png/webp）
    - question: 可选的自定义问题（默认使用火情识别专业提示词）
    """
    if not vision_available():
        return {"code": 200, "message": "success", "data": {
            "ok": False, "detail": f"未配置 API Key 或视觉模型（当前: {settings.VISION_MODEL or '未设置'}）",
        }}
    # 读取并校验图片
    content = await file.read()
    if len(content) > 10 * 1024 * 1024:
        return {"code": 200, "message": "success", "data": {"ok": False, "detail": "图片不能超过 10MB"}}
    suffix = (file.filename or "").rsplit(".", 1)[-1].lower()
    if suffix not in ("jpg", "jpeg", "png", "webp", "bmp"):
        return {"code": 200, "message": "success", "data": {"ok": False, "detail": "仅支持 jpg/png/webp/bmp 格式"}}
    mime = {"jpg": "jpeg", "jpeg": "jpeg", "png": "png", "webp": "webp", "bmp": "bmp"}[suffix]

    try:
        b64 = base64.b64encode(content).decode()
        prompt = question.strip() or FIRE_VISION_PROMPT
        llm = get_vision_llm()
        resp = llm.invoke([HumanMessage(content=[
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": f"data:image/{mime};base64,{b64}"}},
        ])])

        # 保存图片到本地并落库（识别历史）
        rec_id = None
        try:
            os.makedirs(VISION_UPLOAD_DIR, exist_ok=True)
            save_name = f"{uuid.uuid4().hex}.{suffix}"
            with open(os.path.join(VISION_UPLOAD_DIR, save_name), "wb") as f:
                f.write(content)
            rec = VisionHistory(
                user_id=current.id,
                filename=file.filename,
                image_path=save_name,
                analysis=resp.content,
                model=settings.VISION_MODEL,
            )
            db.add(rec)
            db.commit()
            db.refresh(rec)
            rec_id = rec.id
        except Exception:
            db.rollback()  # 历史保存失败不影响识别结果返回

        return {"code": 200, "message": "success", "data": {
            "ok": True,
            "id": rec_id,
            "model": settings.VISION_MODEL,
            "analysis": resp.content,
            "filename": file.filename,
            "question": prompt,
        }}
    except Exception as e:
        return {"code": 200, "message": "success", "data": {
            "ok": False, "detail": f"视觉模型调用失败: {str(e)[:200]}",
        }}


# ====== 视觉：识别历史 ======

def _vh_dict(r: VisionHistory) -> dict:
    return {
        "id": r.id, "filename": r.filename, "model": r.model,
        "analysis": r.analysis,
        "created_at": r.created_at.strftime("%Y-%m-%d %H:%M:%S") if r.created_at else "",
        "has_image": bool(r.image_path),
    }


@router.get("/history")
async def list_vision_history(current: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """识别历史列表（普通用户仅见自己记录，管理员可见全部）"""
    q = db.query(VisionHistory)
    if current.role != "admin":
        q = q.filter(VisionHistory.user_id == current.id)
    rows = q.order_by(VisionHistory.created_at.desc()).limit(100).all()
    return {"code": 200, "message": "success", "data": [_vh_dict(r) for r in rows]}


@router.get("/history/{rec_id}")
async def get_vision_history(rec_id: int, current: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """识别历史详情（用户数据隔离）"""
    r = db.query(VisionHistory).filter(VisionHistory.id == rec_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="记录不存在")
    if current.role != "admin" and r.user_id != current.id:
        raise HTTPException(status_code=403, detail="无权访问该记录")
    return {"code": 200, "message": "success", "data": _vh_dict(r)}


@router.delete("/history/{rec_id}")
async def delete_vision_history(rec_id: int, current: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """删除识别历史（连同本地图片）"""
    r = db.query(VisionHistory).filter(VisionHistory.id == rec_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="记录不存在")
    if current.role != "admin" and r.user_id != current.id:
        raise HTTPException(status_code=403, detail="无权删除该记录")
    if r.image_path:
        try:
            p = os.path.join(VISION_UPLOAD_DIR, r.image_path)
            if os.path.exists(p):
                os.remove(p)
        except Exception:
            pass
    db.delete(r)
    db.commit()
    return {"code": 200, "message": "deleted"}


@router.get("/image/{rec_id}")
async def get_vision_image(rec_id: int, current: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """获取识别历史对应图片（用户数据隔离）"""
    r = db.query(VisionHistory).filter(VisionHistory.id == rec_id).first()
    if not r or not r.image_path:
        raise HTTPException(status_code=404, detail="图片不存在")
    if current.role != "admin" and r.user_id != current.id:
        raise HTTPException(status_code=403, detail="无权访问")
    p = os.path.join(VISION_UPLOAD_DIR, r.image_path)
    if not os.path.exists(p):
        raise HTTPException(status_code=404, detail="图片文件已丢失")
    return FileResponse(p)


# ====== 语音：识别（ASR） ======

@router.post("/audio/transcriptions")
async def asr_transcribe(
    file: UploadFile = File(...),
    current: User = Depends(get_current_user),
):
    """
    语音识别：上传音频文件 → 返回识别文本

    模型: ASR_MODEL（qwen3-asr-flash / paraformer-v2）
    支持 wav / mp3 / opus / aac / amr 格式（前端已编码为 wav），限 20MB。
    """
    content = await file.read()
    if len(content) > 20 * 1024 * 1024:
        return {"code": 200, "message": "success", "data": {"ok": False, "detail": "音频不能超过 20MB"}}
    try:
        text = transcribe_audio(content, file.filename or "audio.webm")
        return {"code": 200, "message": "success", "data": {
            "ok": True, "model": settings.ASR_MODEL, "text": text,
        }}
    except Exception as e:
        return {"code": 200, "message": "success", "data": {
            "ok": False, "detail": f"语音识别失败: {str(e)[:200]}",
        }}


# ====== 语音：合成（TTS） ======

@router.post("/audio/speech")
async def tts_speak(
    req: SpeechRequest,
    current: User = Depends(get_current_user),
):
    """
    语音合成：文本 → mp3 音频流

    模型: TTS_MODEL（qwen3-tts-flash / cosyvoice-v2）
    文本限 500 字（超出自动截断）。
    """
    text = (req.text or "").strip()[:500]
    if not text:
        raise HTTPException(status_code=400, detail="文本不能为空")
    try:
        audio = synthesize_speech(text)
        return Response(
            content=audio,
            media_type="audio/wav",
            headers={"Content-Disposition": "inline; filename=speech.wav"},
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"语音合成失败: {str(e)[:200]}")
