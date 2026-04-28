"""
JWT 认证模块
- Token 生成与验证
- 用户密码哈希
- FastAPI 依赖注入（get_current_user / require_role）
"""
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, HTTPException, Query, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from passlib.context import CryptContext

ALGORITHM = "HS256"

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
_bearer = HTTPBearer(auto_error=False)


def _get_secret_key() -> str:
    key = os.environ.get("YOLO_AUTH_SECRET_KEY", "")
    if not key or key == "change_me_to_a_random_32_byte_hex_string":
        raise RuntimeError(
            "YOLO_AUTH_SECRET_KEY 未设置或仍为默认值，请在 .env 中配置真实密钥"
        )
    return key


# ------------------------------------------------------------------ #
#  密码工具
# ------------------------------------------------------------------ #

def hash_password(plain: str) -> str:
    return pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


# ------------------------------------------------------------------ #
#  Token 工具
# ------------------------------------------------------------------ #

def create_access_token(username: str, role: str, expire_minutes: int = 60) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=expire_minutes)
    payload = {"sub": username, "role": role, "exp": expire}
    return jwt.encode(payload, _get_secret_key(), algorithm=ALGORITHM)


def decode_token(token: str) -> dict:
    """解码并验证 Token，失败抛出 HTTPException 401。"""
    try:
        payload = jwt.decode(token, _get_secret_key(), algorithms=[ALGORITHM])
        if not payload.get("sub"):
            raise ValueError("missing sub")
        return payload
    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token 无效或已过期",
            headers={"WWW-Authenticate": "Bearer"},
        ) from e


# ------------------------------------------------------------------ #
#  FastAPI 依赖
# ------------------------------------------------------------------ #

def _extract_token(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
    token_query: Optional[str] = Query(None, alias="token"),
) -> str:
    """从 Authorization Header 或 ?token= 查询参数中提取 Token。"""
    if credentials and credentials.credentials:
        return credentials.credentials
    if token_query:
        return token_query
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="未提供认证 Token",
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_user(token: str = Depends(_extract_token)) -> dict:
    """返回当前用户 payload（含 sub、role）。"""
    return decode_token(token)


def require_role(*roles: str):
    """工厂函数，返回限制角色的依赖。"""
    def _dep(user: dict = Depends(get_current_user)) -> dict:
        if user.get("role") not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"需要角色: {', '.join(roles)}",
            )
        return user
    return _dep


# 预定义常用角色依赖
require_operator = require_role("operator", "admin")
require_admin = require_role("admin")
