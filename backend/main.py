import asyncio
import sys
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional
from datetime import datetime, timedelta

ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query, HTTPException, Request
from fastapi.responses import HTMLResponse, StreamingResponse, FileResponse, JSONResponse
import uvicorn

from backend.camera import CameraManager
from backend.config import load_and_validate_config, ConfigError
from backend.logging_system import structured_logger
from backend.schemas import DetectionConfig
from backend.database import DatabaseManager
from backend.redis_stats import RedisStats
from backend.notifier import FeishuNotifier

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
        # 计算下次执行时间
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
#  应用生命周期（lifespan）
# ------------------------------------------------------------------ #

@asynccontextmanager
async def lifespan(app: FastAPI):
    global _event_loop, config, db_manager, redis_stats, _cleanup_task, feishu_notifier
    _event_loop = asyncio.get_running_loop()

    # ── 启动阶段 ──
    # 1. 加载并校验配置（支持环境变量指定配置文件）
    import os
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

    # 2. 初始化 MySQL
    if config.get("database"):
        try:
            db_manager = DatabaseManager(config["database"])
            db_manager.create_tables()
            print("数据库连接成功")
        except Exception as e:
            print(f"[WARN] 数据库连接失败（告警将不持久化）: {e}")
            db_manager = None

    # 3. 初始化 Redis（可选）
    if config.get("redis"):
        try:
            redis_stats = RedisStats(config["redis"])
            if redis_stats.is_enabled():
                print("Redis 连接成功")
        except Exception as e:
            print(f"[WARN] Redis 连接失败（实时统计不可用）: {e}")
            redis_stats = None

    # 4. 初始化飞书推送（可选）
    feishu_cfg = config.get("notifications", {}).get("feishu", {})
    if feishu_cfg.get("enabled"):
        try:
            feishu_notifier = FeishuNotifier(feishu_cfg)
            # 注入截图根目录，供上传图片时拼接相对路径
            save_dir = config.get("alert", {}).get("screenshot", {}).get("save_dir", "data/screenshots")
            feishu_notifier._screenshots_root = ROOT / save_dir
            print("飞书推送已启用")
        except Exception as e:
            print(f"[WARN] 飞书推送初始化失败: {e}")
            feishu_notifier = None

    # 5. 启动截图定时清理任务
    _cleanup_task = asyncio.create_task(_run_cleanup())

    # 6. 初始化所有配置的摄像头
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

    yield  # ── 应用运行阶段 ──

    # ── 关闭阶段 ──
    # 1. 停止所有摄像头线程
    for cam in cameras.values():
        try:
            cam.stop()
            if redis_stats and redis_stats.is_enabled():
                redis_stats.set_camera_offline(cam.camera_id)
        except Exception:
            pass

    # 2. 停止清理任务
    if _cleanup_task and not _cleanup_task.done():
        _cleanup_task.cancel()
        try:
            await _cleanup_task
        except asyncio.CancelledError:
            pass

    structured_logger.log("info", "app.shutdown", "服务已关闭")


app = FastAPI(title="智能视频监控", lifespan=lifespan)


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

    # 飞书推送（线程安全：camera 线程 → 主事件循环）
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
        # 从配置列表中查找摄像头配置，或使用传入的 cam_cfg
        if cam_cfg is None:
            cameras_list = config.get("cameras", [])
            cam_cfg = next((c for c in cameras_list if c.get("id") == camera_id), {})

        alert_cfg = config.get("alert", {})
        screenshot_cfg = alert_cfg.get("screenshot", {})
        det_cfg = config.get("detection", {})

        auto_resolution = cam_cfg.get("auto_resolution", True)
        width = None if auto_resolution else cam_cfg.get("width")
        height = None if auto_resolution else cam_cfg.get("height")

        # GPU 设备选择
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


# ------------------------------------------------------------------ #
#  WebSocket /ws/alert
# ------------------------------------------------------------------ #

@app.websocket("/ws/alert")
async def websocket_alert(websocket: WebSocket):
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


# ------------------------------------------------------------------ #
#  视频流
# ------------------------------------------------------------------ #

@app.get("/video_feed")
async def video_feed(camera_id: int = 0):
    camera = get_camera(camera_id)
    return StreamingResponse(
        camera.get_frame_generator(),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


# ------------------------------------------------------------------ #
#  摄像头配置 & 状态
# ------------------------------------------------------------------ #

@app.post("/api/camera/{camera_id}/config")
async def update_config(camera_id: int, cfg: DetectionConfig):
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


@app.get("/api/camera/{camera_id}/status")
async def camera_status(camera_id: int):
    return get_camera(camera_id).get_status()


# ------------------------------------------------------------------ #
#  日志查询
# ------------------------------------------------------------------ #

@app.get("/api/logs")
async def get_logs(limit: int = Query(100, ge=1, le=500)):
    logs = structured_logger.get_recent_logs(limit)
    return {"count": len(logs), "logs": logs}


# ------------------------------------------------------------------ #
#  健康检查（细化）
# ------------------------------------------------------------------ #

@app.get("/health")
async def health():
    camera_stats = [cam.get_status() for cam in cameras.values()]

    # db 子状态
    db_ok = False
    if db_manager:
        try:
            from sqlalchemy import text
            with db_manager.engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            db_ok = True
        except Exception:
            db_ok = False

    # redis 子状态
    redis_ok = redis_stats.is_enabled() if redis_stats else False

    # model 子状态（任意摄像头模型已加载则视为 ok）
    model_ok = any(s.get("model_loaded") for s in camera_stats) if camera_stats else False

    # 总体状态
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
            "redis": "ok" if redis_ok else ("disabled" if not (redis_stats and redis_stats.enabled) else "error"),
            "model": "ok" if model_ok else ("not_loaded" if camera_stats else "no_camera"),
        },
        "cameras": camera_stats,
    }


# ------------------------------------------------------------------ #
#  告警历史查询
# ------------------------------------------------------------------ #

@app.get("/api/alerts")
async def get_alerts(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    camera_id: Optional[int] = Query(None),
    start_time: Optional[str] = Query(None),
    end_time: Optional[str] = Query(None),
    level: Optional[str] = Query(None),
    order: str = Query("desc", pattern="^(asc|desc)$"),
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


@app.get("/api/alerts/{alert_id}/screenshot")
async def get_alert_screenshot(alert_id: int):
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


# ------------------------------------------------------------------ #
#  手动清理（测试用）
# ------------------------------------------------------------------ #

@app.post("/api/cleanup")
async def manual_cleanup():
    """手动触发截图和数据库清理（测试用）"""
    if not config:
        raise HTTPException(status_code=503, detail="配置未加载")

    retention_days = (
        config.get("alert", {}).get("screenshot", {}).get("retention_days", 30)
    )
    save_dir = (
        config.get("alert", {}).get("screenshot", {}).get("save_dir", "data/screenshots")
    )

    try:
        await asyncio.get_running_loop().run_in_executor(
            None, _do_cleanup, save_dir, retention_days
        )
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


# ------------------------------------------------------------------ #
#  实时统计数据
# ------------------------------------------------------------------ #

@app.get("/api/stats")
async def get_stats():
    if not redis_stats or not redis_stats.is_enabled():
        return JSONResponse(status_code=503, content={"error": "Redis 统计功能未启用"})
    try:
        return redis_stats.get_all_stats()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取统计数据失败: {e}")


# ------------------------------------------------------------------ #
#  摄像头动态管理 API
# ------------------------------------------------------------------ #

@app.get("/api/cameras")
async def list_cameras():
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
            # 前端统一使用 id 字段
            item["id"] = cam_id
        else:
            item.update({"connected": False, "running": False, "model_loaded": False})
        result.append(item)
    return {"cameras": result, "total": len(result)}


@app.post("/api/cameras/{camera_id}/add")
async def add_camera(camera_id: int, request: Request):
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


@app.post("/api/cameras/{camera_id}/remove")
async def remove_camera(camera_id: int):
    if camera_id not in cameras:
        raise HTTPException(status_code=404, detail=f"摄像头 {camera_id} 不存在")

    cam = cameras.pop(camera_id)
    try:
        cam.stop()
        if redis_stats and redis_stats.is_enabled():
            redis_stats.set_camera_offline(camera_id)
    except Exception:
        pass

    entry = structured_logger.log(
        "info", "camera.removed", f"摄像头 {camera_id} 已移除",
        camera_id=camera_id,
    )
    _dispatch_signal(entry)
    return {"success": True, "camera_id": camera_id}


# ------------------------------------------------------------------ #
#  前端页面
# ------------------------------------------------------------------ #

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
