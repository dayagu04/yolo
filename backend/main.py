import asyncio
import os
import sys
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional
from datetime import datetime, timedelta

ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query, HTTPException, Request, Depends, APIRouter
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse, FileResponse, JSONResponse, RedirectResponse
import uvicorn

from backend.camera import CameraManager
from backend.config import load_and_validate_config, ConfigError
from backend.logging_system import structured_logger
from backend.schemas import DetectionConfig, LoginRequest, TokenResponse, UserInfo
from backend.database import DatabaseManager
from backend.redis_stats import RedisStats
from backend.notifier import FeishuNotifier
from backend.auth import (
    hash_password, verify_password, create_access_token,
    get_current_user, require_operator, require_admin,
)

# ------------------------------------------------------------------ #
#  全局状态
# ------------------------------------------------------------------ #

START_TS = time.time()
cameras: dict[int, CameraManager] = {}
_ws_clients: list[WebSocket] = []
_event_loop: Optional[asyncio.AbstractEventLoop] = None
config: dict = {}
db_manager: Optional[DatabaseManager] = None
redis_stats: Optional[RedisStats] = None
_cleanup_task: Optional[asyncio.Task] = None
feishu_notifier: Optional[FeishuNotifier] = None


# ------------------------------------------------------------------ #
#  截图定时清理任务
# ------------------------------------------------------------------ #

async def _run_cleanup():
    """按 system.cleanup_schedule 每天执行一次清理"""
    schedule = config.get("system", {}).get("cleanup_schedule", "03:00")
    retention_days = (
        config.get("alert", {}).get("screenshot", {}).get("retention_days", 30)
    )
    save_dir = (
        config.get("alert", {}).get("screenshot", {}).get("save_dir", "data/screenshots")
    )

    while True:
        now = datetime.now()
        try:
            hour, minute = map(int, schedule.split(":"))
        except Exception:
            hour, minute = 3, 0

        next_run = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if next_run <= now:
            next_run += timedelta(days=1)

        wait_sec = (next_run - now).total_seconds()
        await asyncio.sleep(wait_sec)

        await asyncio.get_running_loop().run_in_executor(
            None, _do_cleanup, save_dir, retention_days
        )


def _do_cleanup(save_dir: str, retention_days: int):
    """执行截图与数据库清理（在线程池中运行）"""
    try:
        screenshots_root = ROOT / save_dir
        cutoff = datetime.now() - timedelta(days=retention_days)
        removed_dirs = 0

        if screenshots_root.exists():
            for day_dir in sorted(screenshots_root.iterdir()):
                if not day_dir.is_dir():
                    continue
                try:
                    dir_date = datetime.strptime(day_dir.name, "%Y-%m-%d")
                    if dir_date < cutoff:
                        import shutil
                        shutil.rmtree(day_dir, ignore_errors=True)
                        removed_dirs += 1
                except ValueError:
                    pass

        db_deleted = 0
        if db_manager:
            db_deleted = db_manager.delete_old_alerts(days=retention_days)

        structured_logger.log(
            "info", "system.cleanup_done",
            f"定时清理完成: 删除 {removed_dirs} 个目录, {db_deleted} 条数据库记录",
            data={"removed_dirs": removed_dirs, "db_deleted": db_deleted,
                  "retention_days": retention_days},
        )
    except Exception as e:
        structured_logger.log(
            "error", "system.cleanup_failed", f"定时清理失败: {e}"
        )


# ------------------------------------------------------------------ #
#  审计日志辅助函数
# ------------------------------------------------------------------ #

def _audit(username: str, action: str, resource: str = "", detail: str = "",
           ip_address: str = "", user_agent: str = ""):
    """写入审计日志（同步，用于异步路由中的快速调用）"""
    if db_manager:
        try:
            db_manager.create_audit_log(
                username=username, action=action, resource=resource,
                detail=detail, ip_address=ip_address, user_agent=user_agent,
            )
        except Exception as e:
            structured_logger.log("warning", "audit.write_failed", f"审计日志写入失败: {e}")


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else ""


# ------------------------------------------------------------------ #
#  应用生命周期（lifespan）
# ------------------------------------------------------------------ #

@asynccontextmanager
async def lifespan(app: FastAPI):
    global _event_loop, config, db_manager, redis_stats, _cleanup_task, feishu_notifier
    _event_loop = asyncio.get_running_loop()

    # ── 启动阶段 ──
    config_file = os.environ.get("CONFIG_FILE", "config.yaml")
    try:
        config = load_and_validate_config(ROOT / config_file)
        print(f"已加载配置文件: {config_file}")
    except ConfigError as e:
        print(f"\n[ERROR] 配置校验失败，服务无法启动:\n{e}\n")
        raise SystemExit(1)
    except Exception as e:
        print(f"\n[ERROR] 配置加载异常: {e}\n")
        raise SystemExit(1)

    if config.get("database"):
        try:
            db_manager = DatabaseManager(config["database"])
            db_manager.create_tables()
            print("数据库连接成功")
            _init_admin(db_manager, config)
        except Exception as e:
            print(f"[WARN] 数据库连接失败（告警将不持久化）: {e}")
            db_manager = None

    if config.get("redis"):
        try:
            redis_stats = RedisStats(config["redis"])
            if redis_stats.is_enabled():
                print("Redis 连接成功")
        except Exception as e:
            print(f"[WARN] Redis 连接失败（实时统计不可用）: {e}")
            redis_stats = None

    feishu_cfg = config.get("notifications", {}).get("feishu", {})
    if feishu_cfg.get("enabled"):
        try:
            feishu_notifier = FeishuNotifier(feishu_cfg)
            save_dir = config.get("alert", {}).get("screenshot", {}).get("save_dir", "data/screenshots")
            feishu_notifier._screenshots_root = ROOT / save_dir
            print("飞书推送已启用")
        except Exception as e:
            print(f"[WARN] 飞书推送初始化失败: {e}")
            feishu_notifier = None

    _cleanup_task = asyncio.create_task(_run_cleanup())

    cameras_cfg = config.get("cameras", [])
    if cameras_cfg:
        print(f"初始化 {len(cameras_cfg)} 个摄像头...")
        for cam_cfg in cameras_cfg:
            try:
                get_camera(cam_cfg["id"], cam_cfg)
                print(f"  - 摄像头 {cam_cfg['id']} ({cam_cfg.get('name', 'N/A')}) 已启动")
            except Exception as e:
                print(f"  - 摄像头 {cam_cfg['id']} 启动失败: {e}")

    structured_logger.log("info", "app.startup", "服务启动完成")

    yield

    # ── 关闭阶段 ──
    for cam in cameras.values():
        try:
            cam.stop()
            if redis_stats and redis_stats.is_enabled():
                redis_stats.set_camera_offline(cam.camera_id)
        except Exception:
            pass

    if _cleanup_task and not _cleanup_task.done():
        _cleanup_task.cancel()
        try:
            await _cleanup_task
        except asyncio.CancelledError:
            pass

    structured_logger.log("info", "app.shutdown", "服务已关闭")


app = FastAPI(title="智能视频监控", lifespan=lifespan)

# CORS
_cors_origins = config.get("auth", {}).get("cors_origins", ["http://localhost:8000", "http://127.0.0.1:8000"])
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

# ------------------------------------------------------------------ #
#  API v1 路由器
# ------------------------------------------------------------------ #

api_v1 = APIRouter(prefix="/api/v1")


def _init_admin(db: DatabaseManager, cfg: dict):
    """首次启动时若无用户则创建 admin 账号。"""
    if db.user_exists():
        return
    init_pwd = os.environ.get("YOLO_AUTH_INIT_ADMIN_PASSWORD", "")
    username = cfg.get("auth", {}).get("init_admin_username", "admin")
    if not init_pwd:
        print("[WARN] 未设置 YOLO_AUTH_INIT_ADMIN_PASSWORD，跳过 admin 初始化")
        return
    db.create_user(username, hash_password(init_pwd), role="admin")
    print(f"[INFO] 初始管理员账号已创建: {username}")


# ------------------------------------------------------------------ #
#  WebSocket 广播
# ------------------------------------------------------------------ #

async def _broadcast(message: dict):
    dead: list[WebSocket] = []
    for ws in _ws_clients:
        try:
            await ws.send_json(message)
        except Exception:
            dead.append(ws)
    for ws in dead:
        if ws in _ws_clients:
            _ws_clients.remove(ws)


def _dispatch_signal(message: dict):
    if _event_loop is not None and _event_loop.is_running():
        _event_loop.call_soon_threadsafe(asyncio.create_task, _broadcast(message))


# ------------------------------------------------------------------ #
#  摄像头信号回调（camera 线程 → 主事件循环）
# ------------------------------------------------------------------ #

def _camera_signal_callback(message: dict):
    if message.get("type") == "log":
        structured_logger._buffer.append(message)

    if message.get("type") == "alert" and feishu_notifier:
        screenshot_path = message.get("data", {}).get("screenshot_path")
        if _event_loop is not None and _event_loop.is_running():
            _event_loop.call_soon_threadsafe(
                asyncio.create_task,
                feishu_notifier.send_alert(message, screenshot_path),
            )

    _dispatch_signal(message)


# ------------------------------------------------------------------ #
#  摄像头工厂
# ------------------------------------------------------------------ #

def get_camera(camera_id: int = 0, cam_cfg: Optional[dict] = None) -> CameraManager:
    if camera_id not in cameras:
        if cam_cfg is None:
            cameras_list = config.get("cameras", [])
            cam_cfg = next((c for c in cameras_list if c.get("id") == camera_id), {})

        alert_cfg = config.get("alert", {})
        screenshot_cfg = alert_cfg.get("screenshot", {})
        det_cfg = config.get("detection", {})

        auto_resolution = cam_cfg.get("auto_resolution", True)
        width = None if auto_resolution else cam_cfg.get("width")
        height = None if auto_resolution else cam_cfg.get("height")

        gpu_enabled = det_cfg.get("gpu_enabled", False)
        device = det_cfg.get("device", "cpu") if gpu_enabled else "cpu"

        cameras[camera_id] = CameraManager(
            camera_id=camera_id,
            source=cam_cfg.get("source", camera_id),
            width=width,
            height=height,
            device=device,
            signal_callback=_camera_signal_callback,
            db_manager=db_manager,
            redis_stats=redis_stats,
            screenshot_config=screenshot_cfg,
        )

        if det_cfg.get("conf_threshold") is not None:
            cameras[camera_id].conf_threshold = float(det_cfg["conf_threshold"])
        if det_cfg.get("detect_every_n") is not None:
            cameras[camera_id].detect_every_n = int(det_cfg["detect_every_n"])

        if alert_cfg.get("cooldown_sec") is not None:
            cameras[camera_id]._alert_cooldown_sec = float(alert_cfg["cooldown_sec"])
        if alert_cfg.get("track_ttl_sec") is not None:
            cameras[camera_id]._track_ttl_sec = float(alert_cfg["track_ttl_sec"])

        cameras[camera_id].start()

        if redis_stats and redis_stats.is_enabled():
            redis_stats.set_camera_online(camera_id)

        entry = structured_logger.log(
            "info", "camera.created", "摄像头实例已创建",
            camera_id=camera_id,
            data={"name": cam_cfg.get("name", ""), "source": str(cam_cfg.get("source", camera_id))},
        )
        _dispatch_signal(entry)
    return cameras[camera_id]


# ================================================================== #
#  API v1 路由：认证
# ================================================================== #

@api_v1.post("/auth/login", response_model=TokenResponse)
async def login(req: LoginRequest, request: Request):
    if not db_manager:
        raise HTTPException(status_code=503, detail="数据库未配置")
    user = db_manager.get_user_by_username(req.username)
    if not user or not verify_password(req.password, user["hashed_password"]):
        _audit(req.username, "login_failed", ip_address=_client_ip(request))
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    if not user.get("is_active"):
        raise HTTPException(status_code=403, detail="账号已禁用")

    expire_min = config.get("auth", {}).get("access_token_expire_minutes", 60)
    token = create_access_token(user["username"], user["role"], expire_minutes=expire_min)
    _audit(req.username, "login", ip_address=_client_ip(request),
           user_agent=request.headers.get("user-agent", ""))
    return TokenResponse(access_token=token, expires_in=expire_min * 60, role=user["role"])


@api_v1.get("/auth/me", response_model=UserInfo)
async def get_me(user: dict = Depends(get_current_user)):
    return UserInfo(username=user["sub"], role=user["role"])


# ================================================================== #
#  API v1 路由：摄像头管理
# ================================================================== #

@api_v1.get("/cameras")
async def list_cameras(_user: dict = Depends(get_current_user)):
    cameras_cfg = config.get("cameras", [])
    result = []
    for cam_cfg in cameras_cfg:
        cam_id = cam_cfg["id"]
        cam = cameras.get(cam_id)
        item = {
            "id": cam_id,
            "name": cam_cfg.get("name", f"Camera {cam_id}"),
            "location": cam_cfg.get("location", ""),
            "source": str(cam_cfg.get("source", cam_id)),
        }
        if cam:
            item.update(cam.get_status())
            item["id"] = cam_id
        else:
            item.update({"connected": False, "running": False, "model_loaded": False})
        result.append(item)
    return {"cameras": result, "total": len(result)}


@api_v1.post("/cameras/{camera_id}/config")
async def update_config(camera_id: int, cfg: DetectionConfig, _user: dict = Depends(require_operator)):
    camera = get_camera(camera_id)
    if cfg.enabled is not None:
        camera.toggle_detection(cfg.enabled)
    if cfg.conf is not None:
        camera.set_conf(cfg.conf)
    entry = structured_logger.log(
        "info", "camera.config_updated", "摄像头配置已更新",
        camera_id=camera_id,
        data={"enabled": cfg.enabled, "conf": cfg.conf},
    )
    _dispatch_signal(entry)
    return camera.get_status()


@api_v1.get("/camera/{camera_id}/status")
async def camera_status(camera_id: int, _user: dict = Depends(get_current_user)):
    return get_camera(camera_id).get_status()


@api_v1.post("/cameras/{camera_id}/add")
async def add_camera(camera_id: int, request: Request, _user: dict = Depends(require_operator)):
    if camera_id in cameras:
        raise HTTPException(status_code=409, detail=f"摄像头 {camera_id} 已存在")

    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=422, detail="请求体必须是合法的 JSON")

    source = body.get("source")
    if source is None:
        raise HTTPException(status_code=422, detail="source 字段必填")

    cam_cfg = {
        "id": camera_id,
        "source": source,
        "name": body.get("name", f"Camera {camera_id}"),
        "location": body.get("location", ""),
        "auto_resolution": body.get("auto_resolution", True),
        "width": body.get("width", 1280),
        "height": body.get("height", 720),
    }

    try:
        cam = get_camera(camera_id, cam_cfg)
        _audit(_user["sub"], "camera_add", resource=f"camera:{camera_id}",
               detail=f"name={cam_cfg['name']}, source={source}",
               ip_address=_client_ip(request))
        entry = structured_logger.log(
            "info", "camera.added", f"摄像头 {camera_id} 已动态添加",
            camera_id=camera_id,
            data={"name": cam_cfg["name"], "source": str(source)},
        )
        _dispatch_signal(entry)
        return {
            "id": camera_id,
            "name": cam_cfg["name"],
            "location": cam_cfg["location"],
            "source": str(cam_cfg["source"]),
            **cam.get_status(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"添加摄像头失败: {e}")


@api_v1.post("/cameras/{camera_id}/remove")
async def remove_camera(camera_id: int, request: Request, _user: dict = Depends(require_admin)):
    if camera_id not in cameras:
        raise HTTPException(status_code=404, detail=f"摄像头 {camera_id} 不存在")

    cam = cameras.pop(camera_id)
    try:
        cam.stop()
        if redis_stats and redis_stats.is_enabled():
            redis_stats.set_camera_offline(camera_id)
    except Exception:
        pass

    _audit(_user["sub"], "camera_remove", resource=f"camera:{camera_id}",
           ip_address=_client_ip(request))
    entry = structured_logger.log(
        "info", "camera.removed", f"摄像头 {camera_id} 已移除",
        camera_id=camera_id,
    )
    _dispatch_signal(entry)
    return {"success": True, "camera_id": camera_id}


# ================================================================== #
#  API v1 路由：告警与日志
# ================================================================== #

@api_v1.get("/alerts")
async def get_alerts(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    camera_id: Optional[int] = Query(None),
    start_time: Optional[str] = Query(None),
    end_time: Optional[str] = Query(None),
    level: Optional[str] = Query(None),
    order: str = Query("desc", pattern="^(asc|desc)$"),
    _user: dict = Depends(get_current_user),
):
    if not db_manager:
        raise HTTPException(status_code=503, detail="数据库未配置")
    try:
        start_dt = datetime.fromisoformat(start_time) if start_time else None
        end_dt = datetime.fromisoformat(end_time) if end_time else None
        result = db_manager.query_alerts(
            limit=limit, offset=offset, camera_id=camera_id,
            start_time=start_dt, end_time=end_dt, level=level, order=order,
        )
        result["limit"] = limit
        result["offset"] = offset
        return result
    except ValueError as e:
        raise HTTPException(status_code=422, detail=f"时间格式错误: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"查询失败: {e}")


@api_v1.get("/alerts/{alert_id}/screenshot")
async def get_alert_screenshot(alert_id: int, _user: dict = Depends(get_current_user)):
    if not db_manager:
        raise HTTPException(status_code=503, detail="数据库未配置")
    try:
        alert = db_manager.get_alert_by_id(alert_id)
        if not alert or not alert.get("screenshot_path"):
            raise HTTPException(status_code=404, detail="截图不存在")

        save_dir = config.get("alert", {}).get("screenshot", {}).get(
            "save_dir", "data/screenshots"
        )
        screenshot_file = ROOT / save_dir / alert["screenshot_path"]
        if not screenshot_file.exists():
            raise HTTPException(status_code=404, detail="截图文件已删除")

        return FileResponse(screenshot_file, media_type="image/jpeg")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取截图失败: {e}")


@api_v1.get("/logs")
async def get_logs(limit: int = Query(100, ge=1, le=500), _user: dict = Depends(get_current_user)):
    logs = structured_logger.get_recent_logs(limit)
    return {"count": len(logs), "logs": logs}


@api_v1.get("/stats")
async def get_stats(_user: dict = Depends(get_current_user)):
    if not redis_stats or not redis_stats.is_enabled():
        return JSONResponse(status_code=503, content={"error": "Redis 统计功能未启用"})
    try:
        return redis_stats.get_all_stats()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取统计数据失败: {e}")


@api_v1.post("/cleanup")
async def manual_cleanup(request: Request, _user: dict = Depends(require_admin)):
    """手动触发截图和数据库清理"""
    if not config:
        raise HTTPException(status_code=503, detail="配置未加载")

    retention_days = config.get("alert", {}).get("screenshot", {}).get("retention_days", 30)
    save_dir = config.get("alert", {}).get("screenshot", {}).get("save_dir", "data/screenshots")

    try:
        await asyncio.get_running_loop().run_in_executor(
            None, _do_cleanup, save_dir, retention_days
        )
        _audit(_user["sub"], "manual_cleanup", resource=save_dir,
               detail=f"retention_days={retention_days}", ip_address=_client_ip(request))
        return {
            "status": "ok",
            "message": "清理任务已执行",
            "timestamp": structured_logger._iso_now(),
            "retention_days": retention_days,
            "save_dir": save_dir,
        }
    except Exception as e:
        structured_logger.log("error", "system.cleanup_failed", f"手动清理失败: {e}")
        raise HTTPException(status_code=500, detail=f"清理失败: {e}")


# ================================================================== #
#  API v1 路由：审计日志查询
# ================================================================== #

@api_v1.get("/audit-logs")
async def get_audit_logs(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    username: Optional[str] = Query(None),
    action: Optional[str] = Query(None),
    start_time: Optional[str] = Query(None),
    end_time: Optional[str] = Query(None),
    _user: dict = Depends(require_admin),
):
    if not db_manager:
        raise HTTPException(status_code=503, detail="数据库未配置")
    try:
        start_dt = datetime.fromisoformat(start_time) if start_time else None
        end_dt = datetime.fromisoformat(end_time) if end_time else None
        return db_manager.query_audit_logs(
            limit=limit, offset=offset, username=username,
            action=action, start_time=start_dt, end_time=end_dt,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"查询审计日志失败: {e}")


# ------------------------------------------------------------------ #
#  注册 API v1 路由器
# ------------------------------------------------------------------ #

app.include_router(api_v1)


# ------------------------------------------------------------------ #
#  旧版 /api/ 路由重定向（向后兼容）
# ------------------------------------------------------------------ #

@app.api_route("/api/{path:path}", methods=["GET", "POST"])
async def legacy_api_redirect(path: str, request: Request):
    """将旧版 /api/ 请求重定向到 /api/v1/"""
    new_url = f"/api/v1/{path}"
    if request.url.query:
        new_url += f"?{request.url.query}"
    return RedirectResponse(url=new_url, status_code=307)


# ------------------------------------------------------------------ #
#  非 API 路由（直接挂在 app 上）
# ------------------------------------------------------------------ #

@app.websocket("/ws/alert")
async def websocket_alert(websocket: WebSocket):
    token = websocket.query_params.get("token", "")
    if not token:
        await websocket.close(code=4001)
        return
    try:
        from backend.auth import decode_token
        decode_token(token)
    except Exception:
        await websocket.close(code=4001)
        return

    await websocket.accept()
    _ws_clients.append(websocket)
    entry = structured_logger.log(
        "info", "ws.connected", "WebSocket 客户端连接",
        data={"ws_clients": len(_ws_clients)},
    )
    _dispatch_signal(entry)

    try:
        while True:
            payload = await websocket.receive_text()
            if payload == "ping":
                await websocket.send_json(
                    {"type": "pong", "timestamp": structured_logger._iso_now()}
                )
    except WebSocketDisconnect:
        pass
    finally:
        if websocket in _ws_clients:
            _ws_clients.remove(websocket)
        entry = structured_logger.log(
            "info", "ws.disconnected", "WebSocket 客户端断开",
            data={"ws_clients": len(_ws_clients)},
        )
        _dispatch_signal(entry)


@app.get("/video_feed")
async def video_feed(camera_id: int = 0, _user: dict = Depends(get_current_user)):
    camera = get_camera(camera_id)
    return StreamingResponse(
        camera.get_frame_generator(),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


@app.get("/health")
async def health():
    camera_stats = [cam.get_status() for cam in cameras.values()]

    db_ok = False
    if db_manager:
        try:
            from sqlalchemy import text
            with db_manager.engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            db_ok = True
        except Exception:
            db_ok = False

    redis_ok = redis_stats.is_enabled() if redis_stats else False
    model_ok = any(s.get("model_loaded") for s in camera_stats) if camera_stats else False
    cams_ok = all(s["connected"] and s["model_loaded"] for s in camera_stats) if camera_stats else True
    status = "ok" if (cams_ok and (db_manager is None or db_ok)) else "degraded"

    return {
        "status": status,
        "timestamp": structured_logger._iso_now(),
        "uptime_sec": int(time.time() - START_TS),
        "ws_clients": len(_ws_clients),
        "camera_count": len(cameras),
        "subsystems": {
            "database": "ok" if db_ok else ("disabled" if db_manager is None else "error"),
            "redis": "ok" if redis_ok else ("disabled" if not (redis_stats and redis_stats.is_enabled()) else "error"),
            "model": "ok" if model_ok else ("not_loaded" if camera_stats else "no_camera"),
        },
        "cameras": camera_stats,
    }


FRONTEND = ROOT / "frontend"


@app.get("/", response_class=HTMLResponse)
async def root():
    return HTMLResponse((FRONTEND / "index.html").read_text(encoding="utf-8"))


if __name__ == "__main__":
    import logging
    logging.getLogger("uvicorn.error").setLevel(logging.WARNING)
    srv_cfg = config.get("server", {}) if config else {}
    print("启动监控服务器 -> http://localhost:8000")
    uvicorn.run(
        app,
        host=srv_cfg.get("host", "0.0.0.0"),
        port=srv_cfg.get("port", 8000),
        reload=False,
    )
