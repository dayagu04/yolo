"""
JWT 认证模块
- Token 生成与验证（支持 access + refresh）
- 用户密码哈希
- 登录失败锁定
- 请求限流
- FastAPI 依赖注入（get_current_user / require_role）
"""
import os
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, HTTPException, Query, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from passlib.context import CryptContext

ALGORITHM = "HS256"

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
_bearer = HTTPBearer(auto_error=False)

# ── 登录失败锁定 ──
_login_failures: dict[str, list[float]] = defaultdict(list)
_MAX_ATTEMPTS = int(os.environ.get("YOLO_LOGIN_MAX_ATTEMPTS", "5"))
_LOCKOUT_SECONDS = int(os.environ.get("YOLO_LOGIN_LOCKOUT_SECONDS", "300"))

# ── 请求限流 ──
_rate_limits: dict[str, list[float]] = defaultdict(list)
_DEFAULT_RATE = int(os.environ.get("YOLO_RATE_LIMIT_MAX", "60"))
_DEFAULT_WINDOW = int(os.environ.get("YOLO_RATE_LIMIT_WINDOW", "60"))


def _get_secret_key() -> str:
    key = os.environ.get("YOLO_AUTH_SECRET_KEY", "")
    if not key or key == "change_me_to_a_random_32_byte_hex_string":
        raise RuntimeError(
            "YOLO_AUTH_SECRET_KEY 未设置或仍为默认值，请在 .env 中配置真实密钥"
        )
    if len(key) < 32:
        raise RuntimeError(
            f"YOLO_AUTH_SECRET_KEY 长度不足（当前 {len(key)} 字符，最少 32 字符）"
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
#  登录锁定
# ------------------------------------------------------------------ #

def check_login_allowed(username: str) -> None:
    """检查用户是否被锁定，锁定中则抛出 429。"""
    now = time.time()
    attempts = _login_failures[username]
    # 清理过期记录
    _login_failures[username] = [t for t in attempts if now - t < _LOCKOUT_SECONDS]
    if len(_login_failures[username]) >= _MAX_ATTEMPTS:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"登录失败次数过多，请 {_LOCKOUT_SECONDS // 60} 分钟后重试",
        )


def record_login_failure(username: str) -> None:
    _login_failures[username].append(time.time())


def clear_login_failures(username: str) -> None:
    _login_failures.pop(username, None)


# ------------------------------------------------------------------ #
#  请求限流
# ------------------------------------------------------------------ #

def check_rate_limit(request: Request, max_requests: int = _DEFAULT_RATE, window: int = _DEFAULT_WINDOW) -> None:
    """简单的内存限流，按客户端 IP 限制。支持 X-Forwarded-For。"""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        client_ip = forwarded.split(",")[0].strip()
    else:
        client_ip = request.client.host if request.client else "unknown"
    now = time.time()
    requests = _rate_limits[client_ip]
    _rate_limits[client_ip] = [t for t in requests if now - t < window]
    if len(_rate_limits[client_ip]) >= max_requests:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="请求过于频繁，请稍后重试",
        )
    _rate_limits[client_ip].append(now)


# ------------------------------------------------------------------ #
#  Token 工具
# ------------------------------------------------------------------ #

def create_access_token(username: str, role: str, expire_minutes: int = 60) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=expire_minutes)
    payload = {"sub": username, "role": role, "exp": expire, "type": "access"}
    return jwt.encode(payload, _get_secret_key(), algorithm=ALGORITHM)


def create_refresh_token(username: str, expire_days: int = 7) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=expire_days)
    payload = {"sub": username, "exp": expire, "type": "refresh"}
    return jwt.encode(payload, _get_secret_key(), algorithm=ALGORITHM)


def decode_token(token: str, expected_type: str = "access") -> dict:
    """解码并验证 Token，失败抛出 HTTPException 401。"""
    try:
        payload = jwt.decode(token, _get_secret_key(), algorithms=[ALGORITHM])
        if not payload.get("sub"):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token 缺少用户标识",
                headers={"WWW-Authenticate": "Bearer"},
            )
        if payload.get("type") != expected_type:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token 类型不匹配",
                headers={"WWW-Authenticate": "Bearer"},
            )
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
