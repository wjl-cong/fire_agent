"""
认证 Schema — 注册 / 登录
"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class RegisterRequest(BaseModel):
    username: str = Field(min_length=2, max_length=50)
    email: str = ""
    password: str = Field(min_length=6, max_length=64)


class LoginRequest(BaseModel):
    username: str
    password: str


class UpdateMeRequest(BaseModel):
    """个人资料更新（邮箱）"""
    email: Optional[str] = Field(default=None, max_length=120)


class ChangePasswordRequest(BaseModel):
    """修改密码（需验证旧密码）"""
    old_password: str = Field(min_length=6, max_length=64)
    new_password: str = Field(min_length=6, max_length=64)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    email: Optional[str] = None
    role: str
    created_at: Optional[datetime] = None


class TokenData(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut