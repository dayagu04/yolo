"""系统管理路由：健康检查、资源监控、清理、审计日志、通知配置"""
import asyncio
import time
from datetime import datetime, timedelta
from typing import Optional
from fastapi import APIRouter, HTTPException, Request, Depends, Query
from backend.auth import get_current_user, require_operator, require_admin
from backend.routers.deps import get_db, get_config, get_cameras, get_redis, get_logger, audit

system_router = APIRouter(prefix="/api/v1", tags=["系统"])


@system_router.get("/system/resources")
async def system_resources(request: Request, _user: dict = Depends(require_operator)):
    import psutil
    try:
        cpu = psutil.cpu_percent(interval=0.1)
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage("/")
        result = {
            "cpu_percent": cpu,
            "memory": {"used_mb": mem.used // 1024 // 1024, "total_mb": mem.total // 1024 // 1024, "percent": mem.percent},
            "disk": {"used_gb": round(disk.used / 1024**3, 1), "total_gb": round(disk.total / 1024**3, 1), "percent": disk.percent},
        }
        try:
            import torch
            if torch.cuda.is_available():
                result["gpu"] = {
                    "name": torch.cuda.get_device_name(0),
                    "memory_used_mb": torch.cuda.memory_allocated() // 1024 // 1024,
                    "memory_total_mb": torch.cuda.get_device_properties(0).total_mem // 1024 // 1024,
                }
        except Exception:
            pass  # GPU 检测失败不影响系统资源返回
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取系统资源失败: {e}")


@system_router.post("/cleanup")
async def manual_cleanup(request: Request, _user: dict = Depends(require_admin)):
    config = get_config(request)
    retention_days = config.get("alert", {}).get("screenshot", {}).get("retention_days", 30)
    save_dir = config.get("alert", {}).get("screenshot", {}).get("save_dir", "data/screenshots")
    try:
        from backend.main import _do_cleanup
        await asyncio.get_running_loop().run_in_executor(None, _do_cleanup, save_dir, retention_days)
        audit(request, _user["sub"], "manual_cleanup", resource=save_dir,
              detail=f"retention_days={retention_days}")
        return {"status": "ok", "message": "清理任务已执行", "retention_days": retention_days}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"清理失败: {e}")


@system_router.get("/audit-logs")
async def get_audit_logs(
    request: Request,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    username: Optional[str] = Query(None),
    action: Optional[str] = Query(None),
    start_time: Optional[str] = Query(None),
    end_time: Optional[str] = Query(None),
    _user: dict = Depends(require_admin),
):
    db = get_db(request)
    start_dt = datetime.fromisoformat(start_time) if start_time else None
    end_dt = datetime.fromisoformat(end_time) if end_time else None
    return db.query_audit_logs(
        limit=limit, offset=offset, username=username,
        action=action, start_time=start_dt, end_time=end_dt,
    )


@system_router.get("/notifications/config")
async def get_notification_config(request: Request, _user: dict = Depends(get_current_user)):
    """获取通知渠道配置（脱敏）"""
    config = get_config(request)
    notifs = config.get("notifications", {})
    result = {}
    for name in ["feishu", "wechat_work", "dingtalk", "email", "webhook"]:
        cfg = notifs.get(name, {})
        masked = {"enabled": cfg.get("enabled", False)}
        if "webhook_url" in cfg:
            url = cfg["webhook_url"]
            masked["webhook_url"] = url[:20] + "..." if len(url) > 20 else url
        if "smtp_host" in cfg:
            masked["smtp_host"] = cfg["smtp_host"]
        if "to_addrs" in cfg:
            masked["to_addrs_count"] = len(cfg["to_addrs"])
        result[name] = masked
    return result


@system_router.post("/notifications/{channel}/toggle")
async def toggle_notification(channel: str, request: Request, _user: dict = Depends(require_admin)):
    """运行时开关通知渠道"""
    valid_channels = ["feishu", "wechat_work", "dingtalk", "email", "webhook"]
    if channel not in valid_channels:
        raise HTTPException(status_code=422, detail=f"channel 必须是 {valid_channels} 之一")

    body = await request.json()
    enabled = body.get("enabled")
    if not isinstance(enabled, bool):
        raise HTTPException(status_code=422, detail="enabled 必须是布尔值")

    from backend.main import _extra_notifiers, feishu_notifier
    config = get_config(request)

    # 更新配置
    notifs_cfg = config.setdefault("notifications", {})
    ch_cfg = notifs_cfg.setdefault(channel, {})
    ch_cfg["enabled"] = enabled

    # 飞书特殊处理
    if channel == "feishu" and feishu_notifier:
        feishu_notifier.enabled = enabled

    # 其他渠道：重建列表
    if channel != "feishu":
        from backend.notifiers import WeChatWorkNotifier, DingTalkNotifier, EmailNotifier, WebhookNotifier
        cls_map = {"wechat_work": WeChatWorkNotifier, "dingtalk": DingTalkNotifier,
                   "email": EmailNotifier, "webhook": WebhookNotifier}
        # 移除旧的同类 notifier
        _extra_notifiers[:] = [n for n in _extra_notifiers if not isinstance(n, cls_map.get(channel, type(None)))]
        if enabled and ch_cfg.get("webhook_url") or ch_cfg.get("smtp_host"):
            try:
                _extra_notifiers.append(cls_map[channel](ch_cfg))
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"初始化 {channel} 失败: {e}")

    audit(request, _user["sub"], "notification_toggle", resource=channel,
          detail=f"enabled={enabled}")
    return {"status": "ok", "channel": channel, "enabled": enabled}
