"""
认证接口 — 注册 / 登录 / 当前用户
"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import (
    hash_password,
    verify_password,
    create_access_token,
    get_current_user,
)
from app.models.user import User
from app.schemas.user import (
    ChangePasswordRequest,
    LoginRequest,
    RegisterRequest,
    TokenData,
    UpdateMeRequest,
    UserOut,
)

router = APIRouter()


@router.post("/register")
async def register(req: RegisterRequest, db: Session = Depends(get_db)):
    """用户注册"""
    username = req.username.strip()
    if db.query(User).filter(User.username == username).first():
        raise HTTPException(status_code=400, detail="用户名已存在")
    if req.email and db.query(User).filter(User.email == req.email).first():
        raise HTTPException(status_code=400, detail="邮箱已被使用")

    user = User(
        username=username,
        email=req.email.strip() or None,
        password_hash=hash_password(req.password),
        role="user",
        created_at=datetime.now(),
    )
    db.add(user)
    db.commit()
    db.refresh(user)  # 回填自增 id

    token = create_access_token({"sub": str(user.id)})
    return {"code": 200, "message": "注册成功", "data": TokenData(
        access_token=token,
        user=UserOut.model_validate(user),
    )}


@router.post("/login")
async def login(req: LoginRequest, db: Session = Depends(get_db)):
    """用户登录（同时支持 OAuth2 表单或 JSON）"""
    user = db.query(User).filter(User.username == req.username.strip()).first()
    if not user or not verify_password(req.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
        )
    token = create_access_token({"sub": str(user.id)})
    return {"code": 200, "message": "登录成功", "data": TokenData(
        access_token=token,
        user=UserOut.model_validate(user),
    )}


@router.get("/me")
async def me(current: User = Depends(get_current_user)):
    """获取当前登录用户信息"""
    return {"code": 200, "message": "success", "data": UserOut.model_validate(current)}


@router.put("/me")
async def update_me(req: UpdateMeRequest, current: User = Depends(get_current_user),
                    db: Session = Depends(get_db)):
    """修改个人资料（邮箱）"""
    if req.email is not None:
        email = req.email.strip() or None
        if email and db.query(User).filter(User.email == email, User.id != current.id).first():
            raise HTTPException(status_code=400, detail="邮箱已被其他账号使用")
        current.email = email
        db.commit()
        db.refresh(current)
    return {"code": 200, "message": "资料已更新", "data": UserOut.model_validate(current)}


@router.put("/me/password")
async def change_password(req: ChangePasswordRequest, current: User = Depends(get_current_user),
                          db: Session = Depends(get_db)):
    """修改密码（需验证旧密码；修改后需重新登录）"""
    if not verify_password(req.old_password, current.password_hash):
        raise HTTPException(status_code=400, detail="旧密码错误")
    if req.old_password == req.new_password:
        raise HTTPException(status_code=400, detail="新密码不能与旧密码相同")
    current.password_hash = hash_password(req.new_password)
    db.commit()
    return {"code": 200, "message": "密码已修改，请使用新密码重新登录", "data": {"ok": True}}