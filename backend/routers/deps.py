"""共享依赖：通过 app.state 访问全局对象"""
from fastapi import Request, HTTPException
from backend.database import DatabaseManager
from backend.redis_stats import RedisStats
from backend.logging_system import StructuredLogger


def get_db(request: Request) -> DatabaseManager:
    db = getattr(request.app.state, "db_manager", None)
    if not db:
        raise HTTPException(status_code=503, detail="数据库未配置")
    return db


def get_db_optional(request: Request):
    return getattr(request.app.state, "db_manager", None)


def get_config(request: Request) -> dict:
    return getattr(request.app.state, "config", {})


def get_cameras(request: Request) -> dict:
    return getattr(request.app.state, "cameras", {})


def get_redis(request: Request):
    return getattr(request.app.state, "redis_stats", None)


def get_logger(request: Request) -> StructuredLogger:
    return getattr(request.app.state, "structured_logger", None)


def get_event_loop(request: Request):
    return getattr(request.app.state, "event_loop", None)


def audit(request, username: str, action: str, resource: str = "", detail: str = ""):
    db = get_db_optional(request)
    if db:
        try:
            ip = ""
            forwarded = request.headers.get("x-forwarded-for")
            if forwarded:
                ip = forwarded.split(",")[0].strip()
            elif request.client:
                ip = request.client.host
            db.create_audit_log(
                username=username, action=action, resource=resource,
                detail=detail, ip_address=ip,
                user_agent=request.headers.get("user-agent", ""),
            )
        except Exception:
            pass
