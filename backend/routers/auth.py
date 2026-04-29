"""认证与用户管理路由"""
from fastapi import APIRouter, HTTPException, Request, Depends
from backend.schemas import LoginRequest, TokenResponse, UserInfo
from backend.auth import (
    hash_password, verify_password, create_access_token, create_refresh_token,
    decode_token, check_login_allowed, record_login_failure, clear_login_failures,
    check_rate_limit, get_current_user, require_admin,
)
from backend.routers.deps import get_db, get_config, audit

auth_router = APIRouter(prefix="/api/v1/auth", tags=["认证"])


@auth_router.post("/login", response_model=TokenResponse)
async def login(req: LoginRequest, request: Request):
    db = get_db(request)
    config = get_config(request)

    check_rate_limit(request, max_requests=10, window=60)
    check_login_allowed(req.username)

    user = db.get_user_by_username(req.username)
    if not user or not verify_password(req.password, user["hashed_password"]):
        record_login_failure(req.username)
        audit(request, req.username, "login_failed")
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    if not user.get("is_active"):
        raise HTTPException(status_code=403, detail="账号已禁用")

    clear_login_failures(req.username)
    expire_min = config.get("auth", {}).get("access_token_expire_minutes", 60)
    token = create_access_token(user["username"], user["role"], expire_minutes=expire_min)
    refresh = create_refresh_token(user["username"])
    audit(request, req.username, "login")
    return TokenResponse(
        access_token=token, refresh_token=refresh,
        expires_in=expire_min * 60, role=user["role"],
    )


@auth_router.post("/refresh")
async def refresh_token(request: Request):
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=422, detail="请求体必须是 JSON")

    rt = body.get("refresh_token", "")
    if not rt:
        raise HTTPException(status_code=422, detail="refresh_token 必填")

    try:
        payload = decode_token(rt, expected_type="refresh")
    except HTTPException:
        raise HTTPException(status_code=401, detail="refresh_token 无效或已过期")

    username = payload["sub"]
    db = get_db(request)
    config = get_config(request)
    user = db.get_user_by_username(username)
    if not user or not user.get("is_active"):
        raise HTTPException(status_code=401, detail="用户不存在或已禁用")

    expire_min = config.get("auth", {}).get("access_token_expire_minutes", 60)
    new_token = create_access_token(user["username"], user["role"], expire_minutes=expire_min)
    return {"access_token": new_token, "token_type": "bearer", "expires_in": expire_min * 60}


@auth_router.get("/me", response_model=UserInfo)
async def get_me(user: dict = Depends(get_current_user)):
    return UserInfo(username=user["sub"], role=user["role"])


# ── 用户管理（admin） ──

@auth_router.get("/users")
async def list_users(request: Request, _user: dict = Depends(require_admin)):
    db = get_db(request)
    return db.list_users()


@auth_router.post("/users")
async def create_user(request: Request, _user: dict = Depends(require_admin)):
    db = get_db(request)
    body = await request.json()
    username = body.get("username", "").strip()
    password = body.get("password", "")
    role = body.get("role", "viewer")
    if not username or not password:
        raise HTTPException(status_code=422, detail="username 和 password 必填")
    if role not in ("admin", "operator", "viewer"):
        raise HTTPException(status_code=422, detail="role 必须是 admin/operator/viewer")
    if db.get_user_by_username(username):
        raise HTTPException(status_code=409, detail="用户名已存在")
    user = db.create_user(username, hash_password(password), role=role)
    audit(request, _user["sub"], "user_create", resource=f"user:{username}", detail=f"role={role}")
    return user


@auth_router.put("/users/{user_id}")
async def update_user(user_id: int, request: Request, _user: dict = Depends(require_admin)):
    db = get_db(request)
    body = await request.json()
    updates = {}
    if "role" in body:
        if body["role"] not in ("admin", "operator", "viewer"):
            raise HTTPException(status_code=422, detail="role 无效")
        updates["role"] = body["role"]
    if "is_active" in body:
        updates["is_active"] = bool(body["is_active"])
    if not updates:
        raise HTTPException(status_code=422, detail="无有效更新字段")
    success = db.update_user(user_id, **updates)
    if not success:
        raise HTTPException(status_code=404, detail="用户不存在")
    audit(request, _user["sub"], "user_update", resource=f"user:{user_id}", detail=str(updates))
    return {"status": "ok"}


@auth_router.delete("/users/{user_id}")
async def delete_user(user_id: int, request: Request, _user: dict = Depends(require_admin)):
    db = get_db(request)
    success = db.delete_user(user_id)
    if not success:
        raise HTTPException(status_code=404, detail="用户不存在")
    audit(request, _user["sub"], "user_delete", resource=f"user:{user_id}")
    return {"status": "ok"}


@auth_router.put("/users/{user_id}/password")
async def change_password(user_id: int, request: Request, _user: dict = Depends(get_current_user)):
    db = get_db(request)
    # 只能改自己的密码，除非是 admin
    if _user["role"] != "admin" and user_id != _user.get("id"):
        raise HTTPException(status_code=403, detail="只能修改自己的密码")
    body = await request.json()
    old_password = body.get("old_password", "")
    new_password = body.get("new_password", "")
    if not new_password or len(new_password) < 6:
        raise HTTPException(status_code=422, detail="新密码至少 6 位")
    # admin 改别人密码不需要旧密码
    if _user["role"] != "admin" or user_id == _user.get("id"):
        user = db.get_user_by_username(_user["sub"])
        if not user or not verify_password(old_password, user["hashed_password"]):
            raise HTTPException(status_code=401, detail="旧密码错误")
    success = db.update_password(user_id, hash_password(new_password))
    if not success:
        raise HTTPException(status_code=404, detail="用户不存在")
    audit(request, _user["sub"], "password_change", resource=f"user:{user_id}")
    return {"status": "ok"}
