"""告警、升级、日志、统计路由"""
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, HTTPException, Request, Depends, Query
from fastapi.responses import FileResponse, JSONResponse
from backend.auth import get_current_user, require_operator
from backend.routers.deps import get_db, get_config, get_cameras, get_redis, get_logger

alert_router = APIRouter(prefix="/api/v1", tags=["告警"])


# ── 告警查询 ──

@alert_router.get("/alerts")
async def get_alerts(
    request: Request,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    camera_id: Optional[int] = Query(None),
    start_time: Optional[str] = Query(None),
    end_time: Optional[str] = Query(None),
    level: Optional[str] = Query(None),
    order: str = Query("desc", pattern="^(asc|desc)$"),
    _user: dict = Depends(get_current_user),
):
    db = get_db(request)
    try:
        start_dt = datetime.fromisoformat(start_time) if start_time else None
        end_dt = datetime.fromisoformat(end_time) if end_time else None
        result = db.query_alerts(
            limit=limit, offset=offset, camera_id=camera_id,
            start_time=start_dt, end_time=end_dt, level=level, order=order,
        )
        result["limit"] = limit
        result["offset"] = offset
        return result
    except ValueError as e:
        raise HTTPException(status_code=422, detail=f"时间格式错误: {e}")


@alert_router.get("/alerts/{alert_id}/screenshot")
async def get_alert_screenshot(alert_id: int, request: Request, _user: dict = Depends(get_current_user)):
    from pathlib import Path
    db = get_db(request)
    config = get_config(request)
    alert = db.get_alert_by_id(alert_id)
    if not alert or not alert.get("screenshot_path"):
        raise HTTPException(status_code=404, detail="截图不存在")

    save_dir = config.get("alert", {}).get("screenshot", {}).get("save_dir", "data/screenshots")
    from backend.main import ROOT
    screenshot_file = ROOT / save_dir / alert["screenshot_path"]
    if not screenshot_file.exists():
        raise HTTPException(status_code=404, detail="截图文件已删除")

    return FileResponse(screenshot_file, media_type="image/jpeg")


@alert_router.post("/alerts/{alert_id}/acknowledge")
async def acknowledge_alert(alert_id: int, request: Request, _user: dict = Depends(get_current_user)):
    """确认告警"""
    db = get_db(request)
    from backend.routers.deps import audit
    success = db.acknowledge_alert(alert_id, _user["sub"])
    if not success:
        raise HTTPException(status_code=404, detail="告警不存在或已确认")
    audit(request, _user["sub"], "alert_acknowledge", resource=f"alert:{alert_id}")
    return {"status": "ok"}


# ── 告警升级 ──

@alert_router.get("/escalations/pending")
async def get_pending_escalations(request: Request, _user: dict = Depends(require_operator)):
    db = get_db(request)
    return db.get_pending_escalations()


@alert_router.post("/escalations/{escalation_id}/notify")
async def mark_escalation_notified(escalation_id: int, request: Request, _user: dict = Depends(require_operator)):
    db = get_db(request)
    db.mark_escalation_notified(escalation_id)
    return {"status": "ok"}


@alert_router.get("/alerts/{alert_id}/escalations")
async def get_alert_escalations(alert_id: int, request: Request, _user: dict = Depends(get_current_user)):
    db = get_db(request)
    return db.get_alert_escalations(alert_id)


@alert_router.post("/alerts/{alert_id}/escalate")
async def manual_escalate_alert(alert_id: int, request: Request, _user: dict = Depends(require_operator)):
    db = get_db(request)
    from backend.routers.deps import audit
    body = await request.json()
    new_level = body.get("level")
    if new_level not in ("low", "medium", "high"):
        raise HTTPException(status_code=422, detail="level 必须是 low/medium/high")
    reason = body.get("reason", "手动升级")
    success = db.escalate_alert(alert_id, new_level, reason)
    if not success:
        raise HTTPException(status_code=404, detail="告警不存在或级别未变化")
    audit(request, _user["sub"], "alert_escalate", resource=f"alert:{alert_id}",
          detail=f"升级到 {new_level}: {reason}")
    return {"status": "ok"}


# ── 日志 ──

@alert_router.get("/logs")
async def get_logs(request: Request, limit: int = Query(100, ge=1, le=500), _user: dict = Depends(get_current_user)):
    logger = get_logger(request)
    if not logger:
        return {"count": 0, "logs": []}
    logs = logger.get_recent_logs(limit)
    return {"count": len(logs), "logs": logs}


# ── 统计 ──

@alert_router.get("/stats")
async def get_stats(request: Request, _user: dict = Depends(get_current_user)):
    redis = get_redis(request)
    if not redis or not redis.is_enabled():
        return JSONResponse(status_code=503, content={"error": "Redis 统计功能未启用"})
    return redis.get_all_stats()


@alert_router.get("/stats/trend")
async def get_alert_trend(request: Request, days: int = Query(7, ge=1, le=90), _user: dict = Depends(get_current_user)):
    db = get_db(request)
    return db.get_alert_stats(days=days)


@alert_router.get("/stats/person-trend")
async def get_person_trend(
    request: Request,
    camera_id: Optional[int] = Query(None),
    hours: int = Query(24, ge=1, le=168),
    _user: dict = Depends(get_current_user),
):
    db = get_db(request)
    return db.get_person_trend(camera_id=camera_id, hours=hours)
