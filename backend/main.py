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

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query, HTTPException, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse, FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
import uvicorn

from backend.camera import CameraManager
from backend.config import load_and_validate_config, ConfigError
from backend.logging_system import structured_logger
from backend.database import DatabaseManager
from backend.redis_stats import RedisStats
from backend.notifier import FeishuNotifier
from backend.notifiers import WeChatWorkNotifier, DingTalkNotifier, EmailNotifier, WebhookNotifier
from backend.auth import (
    hash_password, verify_password, create_access_token, create_refresh_token,
    decode_token, get_current_user, require_admin,
)
from backend.routers import auth_router, camera_router, alert_router, roi_router, model_router, system_router

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
_escalation_task: Optional[asyncio.Task] = None
feishu_notifier: Optional[FeishuNotifier] = None
_extra_notifiers: list = []


# ------------------------------------------------------------------ #
#  截图定时清理任务
# ------------------------------------------------------------------ #

async def _run_cleanup():
    schedule = config.get("system", {}).get("cleanup_schedule", "03:00")
    retention_days = config.get("alert", {}).get("screenshot", {}).get("retention_days", 30)
    save_dir = config.get("alert", {}).get("screenshot", {}).get("save_dir", "data/screenshots")

    while True:
        now = datetime.now()
        try:
            hour, minute = map(int, schedule.split(":"))
        except (ValueError, AttributeError):
            hour, minute = 3, 0
        next_run = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if next_run <= now:
            next_run += timedelta(days=1)
        await asyncio.sleep((next_run - now).total_seconds())
        await asyncio.get_running_loop().run_in_executor(None, _do_cleanup, save_dir, retention_days)


def _do_cleanup(save_dir: str, retention_days: int):
    import shutil
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
                        shutil.rmtree(day_dir, ignore_errors=True)
                        removed_dirs += 1
                except ValueError:
                    pass
        db_deleted = 0
        if db_manager:
            db_deleted = db_manager.delete_old_alerts(days=retention_days)
        structured_logger.log("info", "system.cleanup_done",
                              f"定时清理完成: 删除 {removed_dirs} 个目录, {db_deleted} 条记录",
                              data={"removed_dirs": removed_dirs, "db_deleted": db_deleted})
    except Exception as e:
        structured_logger.log("error", "system.cleanup_failed", f"定时清理失败: {e}")


# ------------------------------------------------------------------ #
#  告警升级调度器
# ------------------------------------------------------------------ #

ESCALATION_CHAIN = {
    "low": {"after_sec": 600, "to_level": "medium"},
    "medium": {"after_sec": 300, "to_level": "high"},
}


async def _run_escalation():
    while True:
        await asyncio.sleep(60)
        if not db_manager:
            continue
        try:
            now = datetime.now()
            for from_level, rule in ESCALATION_CHAIN.items():
                alerts = await _event_loop.run_in_executor(
                    None, lambda fl=from_level: db_manager.get_unprocessed_alerts(
                        older_than_sec=rule["after_sec"]))
                for alert in alerts:
                    if alert.get("level") != from_level:
                        continue
                    alert_ts = alert.get("timestamp")
                    if isinstance(alert_ts, str):
                        alert_ts = datetime.fromisoformat(alert_ts)
                    if (now - alert_ts).total_seconds() < rule["after_sec"]:
                        continue
                    success = await _event_loop.run_in_executor(
                        None, lambda a=alert: db_manager.escalate_alert(
                            a["id"], rule["to_level"],
                            f"超过 {rule['after_sec']}s 未处理，自动升级"))
                    if success:
                        structured_logger.log("info", "alert.escalated",
                                              f"告警 #{alert['id']} 自动升级: {from_level}→{rule['to_level']}")
                        escalation_msg = {
                            "type": "alert", "level": rule["to_level"],
                            "message": f"告警升级: #{alert['id']} {from_level}→{rule['to_level']}",
                            "camera_id": alert.get("camera_id"),
                            "data": {"escalation": True, "alert_id": alert["id"],
                                     "from_level": from_level, "to_level": rule["to_level"]},
                        }
                        if feishu_notifier:
                            _event_loop.call_soon_threadsafe(
                                asyncio.create_task, feishu_notifier.send_alert(escalation_msg))
                        for notifier in _extra_notifiers:
                            _event_loop.call_soon_threadsafe(
                                asyncio.create_task, notifier.send_alert(escalation_msg))
        except Exception as e:
            structured_logger.log("error", "escalation.failed", f"告警升级调度失败: {e}")


# ------------------------------------------------------------------ #
#  审计日志辅助
# ------------------------------------------------------------------ #

def _audit(username: str, action: str, resource: str = "", detail: str = "",
           ip_address: str = "", user_agent: str = ""):
    if db_manager:
        try:
            db_manager.create_audit_log(username=username, action=action, resource=resource,
                                        detail=detail, ip_address=ip_address, user_agent=user_agent)
        except Exception as e:
            pass


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else ""


# ------------------------------------------------------------------ #
#  应用生命周期
# ------------------------------------------------------------------ #

def _init_admin(db: DatabaseManager, cfg: dict):
    if db.user_exists():
        return
    init_pwd = os.environ.get("YOLO_AUTH_INIT_ADMIN_PASSWORD", "")
    username = cfg.get("auth", {}).get("init_admin_username", "admin")
    if not init_pwd:
        print("[WARN] 未设置 YOLO_AUTH_INIT_ADMIN_PASSWORD，跳过 admin 初始化")
        return
    db.create_user(username, hash_password(init_pwd), role="admin")
    print(f"[INFO] 初始管理员账号已创建: {username}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _event_loop, config, db_manager, redis_stats, _cleanup_task, _escalation_task
    global feishu_notifier, _extra_notifiers
    _event_loop = asyncio.get_running_loop()

    config_file = os.environ.get("CONFIG_FILE", "config.yaml")
    try:
        config = load_and_validate_config(ROOT / config_file)
        print(f"已加载配置文件: {config_file}")

        # CORS — 在 config 加载后设置（修复时序 Bug）
        _cors_origins = config.get("auth", {}).get("cors_origins", ["http://localhost:8000", "http://127.0.0.1:8000"])
        app.add_middleware(CORSMiddleware, allow_origins=_cors_origins, allow_credentials=True,
                           allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
                           allow_headers=["Authorization", "Content-Type"])
    except ConfigError as e:
        print(f"\n[ERROR] 配置校验失败: {e}\n")
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
            print(f"[WARN] 数据库连接失败: {e}")
            db_manager = None

    if config.get("redis"):
        try:
            redis_stats = RedisStats(config["redis"])
            if redis_stats.is_enabled():
                print("Redis 连接成功")
        except Exception as e:
            print(f"[WARN] Redis 连接失败: {e}")
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

    notifs_cfg = config.get("notifications", {})
    for name, cls in [("wechat_work", WeChatWorkNotifier), ("dingtalk", DingTalkNotifier),
                      ("email", EmailNotifier), ("webhook", WebhookNotifier)]:
        cfg = notifs_cfg.get(name, {})
        if cfg.get("enabled"):
            try:
                _extra_notifiers.append(cls(cfg))
                print(f"{name} 通知已启用")
            except Exception as e:
                print(f"[WARN] {name} 通知初始化失败: {e}")

    # 存入 app.state 供 routers 使用
    app.state.config = config
    app.state.db_manager = db_manager
    app.state.redis_stats = redis_stats
    app.state.cameras = cameras
    app.state.structured_logger = structured_logger
    app.state.event_loop = _event_loop

    _cleanup_task = asyncio.create_task(_run_cleanup())
    _escalation_task = asyncio.create_task(_run_escalation())

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

    for cam in cameras.values():
        try:
            cam.stop()
            if redis_stats and redis_stats.is_enabled():
                redis_stats.set_camera_offline(cam.camera_id)
        except Exception as e:
            logging.getLogger(__name__).warning(f"停止摄像头 {getattr(cam, 'camera_id', '?')} 失败: {e}")

    for task in [_cleanup_task, _escalation_task]:
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    structured_logger.log("info", "app.shutdown", "服务已关闭")


app = FastAPI(title="智能视频监控", lifespan=lifespan)


# ------------------------------------------------------------------ #
#  注册路由
# ------------------------------------------------------------------ #

app.include_router(auth_router)
app.include_router(camera_router)
app.include_router(alert_router)
app.include_router(roi_router)
app.include_router(model_router)
app.include_router(system_router)


# ------------------------------------------------------------------ #
#  旧版 /api/ 重定向
# ------------------------------------------------------------------ #

@app.api_route("/api/{path:path}", methods=["GET", "POST"])
async def legacy_api_redirect(path: str, request: Request):
    new_url = f"/api/v1/{path}"
    if request.url.query:
        new_url += f"?{request.url.query}"
    return RedirectResponse(url=new_url, status_code=307)


# ------------------------------------------------------------------ #
#  WebSocket
# ------------------------------------------------------------------ #

async def _broadcast(message: dict):
    dead: list[WebSocket] = []
    for ws in _ws_clients:
        try:
            await ws.send_json(message)
        except Exception as e:
            dead.append(ws)
    for ws in dead:
        if ws in _ws_clients:
            _ws_clients.remove(ws)


def _dispatch_signal(message: dict):
    if _event_loop is not None and _event_loop.is_running():
        _event_loop.call_soon_threadsafe(asyncio.create_task, _broadcast(message))


def _camera_signal_callback(message: dict):
    if message.get("type") == "log":
        structured_logger._buffer.append(message)
    if message.get("type") == "alert":
        screenshot_path = message.get("data", {}).get("screenshot_path")
        if _event_loop is not None and _event_loop.is_running():
            if feishu_notifier:
                _event_loop.call_soon_threadsafe(
                    asyncio.create_task, feishu_notifier.send_alert(message, screenshot_path))
            for notifier in _extra_notifiers:
                _event_loop.call_soon_threadsafe(
                    asyncio.create_task, notifier.send_alert(message, screenshot_path))
    _dispatch_signal(message)


@app.websocket("/ws/alert")
async def websocket_alert(websocket: WebSocket):
    token = websocket.query_params.get("token", "")
    if not token:
        await websocket.close(code=4001)
        return
    try:
        decode_token(token)
    except Exception as e:
        await websocket.close(code=4001)
        return

    await websocket.accept()
    _ws_clients.append(websocket)
    structured_logger.log("info", "ws.connected", "WebSocket 客户端连接",
                          data={"ws_clients": len(_ws_clients)})

    try:
        while True:
            payload = await websocket.receive_text()
            if payload == "ping":
                await websocket.send_json({"type": "pong", "timestamp": structured_logger._iso_now()})
    except WebSocketDisconnect:
        pass
    finally:
        if websocket in _ws_clients:
            _ws_clients.remove(websocket)
        structured_logger.log("info", "ws.disconnected", "WebSocket 客户端断开",
                              data={"ws_clients": len(_ws_clients)})


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
            width=width, height=height, device=device,
            signal_callback=_camera_signal_callback,
            db_manager=db_manager, redis_stats=redis_stats,
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
        structured_logger.log("info", "camera.created", "摄像头实例已创建",
                              camera_id=camera_id,
                              data={"name": cam_cfg.get("name", ""), "source": str(cam_cfg.get("source", camera_id))})
    return cameras[camera_id]


# ------------------------------------------------------------------ #
#  非 API 路由
# ------------------------------------------------------------------ #

@app.get("/video_feed")
async def video_feed(camera_id: int = 0, _user: dict = Depends(get_current_user)):
    camera = get_camera(camera_id)
    return StreamingResponse(camera.get_frame_generator(),
                             media_type="multipart/x-mixed-replace; boundary=frame")


@app.get("/playback")
async def playback(camera_id: int = 0, seconds: float = 10.0, _user: dict = Depends(get_current_user)):
    camera = get_camera(camera_id)
    frames = camera.get_frame_buffer(seconds)

    async def generate():
        import cv2
        for ts, frame in frames:
            ret, jpeg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
            if ret:
                yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpeg.tobytes() + b"\r\n")
                await asyncio.sleep(0.033)

    return StreamingResponse(generate(), media_type="multipart/x-mixed-replace; boundary=frame")


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
        except Exception as e:
            logging.getLogger(__name__).debug(f"数据库健康检查失败: {e}")

    redis_ok = redis_stats.is_enabled() if redis_stats else False
    model_ok = any(s.get("model_loaded") for s in camera_stats) if camera_stats else False
    cams_ok = all(s["connected"] and s["model_loaded"] for s in camera_stats) if camera_stats else True
    status = "ok" if (cams_ok and (db_manager is None or db_ok)) else "degraded"

    return {
        "status": status, "timestamp": structured_logger._iso_now(),
        "uptime_sec": int(time.time() - START_TS), "ws_clients": len(_ws_clients),
        "camera_count": len(cameras),
        "subsystems": {
            "database": "ok" if db_ok else ("disabled" if db_manager is None else "error"),
            "redis": "ok" if redis_ok else ("disabled" if not (redis_stats and redis_stats.is_enabled()) else "error"),
            "model": "ok" if model_ok else ("not_loaded" if camera_stats else "no_camera"),
        },
        "cameras": camera_stats,
    }


@app.get("/metrics")
async def prometheus_metrics():
    from backend.metrics import collect_metrics
    return HTMLResponse(content=collect_metrics(cameras, db_manager, redis_stats, START_TS, ws_clients=len(_ws_clients)),
                        media_type="text/plain; charset=utf-8")


FRONTEND = ROOT / "frontend"
app.mount("/static", StaticFiles(directory=str(FRONTEND / "static")), name="static")


@app.get("/", response_class=HTMLResponse)
async def root():
    return HTMLResponse((FRONTEND / "index.html").read_text(encoding="utf-8"))


@app.get("/manifest.json")
async def manifest():
    return FileResponse(FRONTEND / "manifest.json", media_type="application/manifest+json")


@app.get("/service-worker.js")
async def service_worker():
    return FileResponse(FRONTEND / "service-worker.js", media_type="application/javascript")


if __name__ == "__main__":
    import logging
    logging.getLogger("uvicorn.error").setLevel(logging.WARNING)
    srv_cfg = config.get("server", {}) if config else {}
    print("启动监控服务器 -> http://localhost:8000")
    uvicorn.run(app, host=srv_cfg.get("host", "0.0.0.0"), port=srv_cfg.get("port", 8000), reload=False)
