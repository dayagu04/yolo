import asyncio
import sys
import time
import yaml
from pathlib import Path
from typing import Optional
from datetime import datetime

# 确保项目根目录在 sys.path 中
ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse, FileResponse, JSONResponse
import uvicorn

from backend.camera import CameraManager
from backend.logging_system import structured_logger
from backend.schemas import DetectionConfig
from backend.database import DatabaseManager
from backend.redis_stats import RedisStats

app = FastAPI(title="智能视频监控")

# ------------------------------------------------------------------ #
#  全局状态
# ------------------------------------------------------------------ #

START_TS = time.time()
cameras: dict[int, CameraManager] = {}
_ws_clients: list[WebSocket] = []
_event_loop: Optional[asyncio.AbstractEventLoop] = None

# 配置与数据库
config: dict = {}
db_manager: Optional[DatabaseManager] = None
redis_stats: Optional[RedisStats] = None


# ------------------------------------------------------------------ #
#  配置加载
# ------------------------------------------------------------------ #

def load_config() -> dict:
    """加载 config.yaml 配置文件"""
    config_path = ROOT / "config.yaml"
    if not config_path.exists():
        raise FileNotFoundError(f"配置文件不存在: {config_path}")

    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


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
    global _event_loop
    if _event_loop is not None and _event_loop.is_running():
        _event_loop.call_soon_threadsafe(asyncio.create_task, _broadcast(message))


# ------------------------------------------------------------------ #
#  摄像头信号回调（camera 线程 -> 主事件循环）
# ------------------------------------------------------------------ #

def _camera_signal_callback(message: dict):
    # log 类型同时写入结构化日志缓冲
    if message.get("type") == "log":
        structured_logger._buffer.append(message)
    _dispatch_signal(message)


# ------------------------------------------------------------------ #
#  应用生命周期
# ------------------------------------------------------------------ #

@app.on_event("startup")
async def on_startup():
    global _event_loop, config, db_manager, redis_stats
    _event_loop = asyncio.get_running_loop()

    # 加载配置
    try:
        config = load_config()
        print(f"配置文件加载成功: {len(config)} 个配置项")
    except Exception as e:
        print(f"配置文件加载失败: {e}")
        config = {}

    # 初始化数据库
    if config.get("database"):
        try:
            db_manager = DatabaseManager(config["database"])
            db_manager.create_tables()
            print("数据库连接成功")
        except Exception as e:
            print(f"数据库连接失败: {e}")
            db_manager = None

    # 初始化 Redis
    if config.get("redis"):
        try:
            redis_stats = RedisStats(config["redis"])
            if redis_stats.is_enabled():
                print("Redis 连接成功")
        except Exception as e:
            print(f"Redis 连接失败: {e}")
            redis_stats = None

    entry = structured_logger.log("info", "app.startup", "服务启动完成")
    _dispatch_signal(entry)


@app.on_event("shutdown")
async def on_shutdown():
    for cam in cameras.values():
        cam.stop()
    structured_logger.log("info", "app.shutdown", "服务已关闭")


# ------------------------------------------------------------------ #
#  摄像头工厂
# ------------------------------------------------------------------ #

def get_camera(camera_id: int = 0) -> CameraManager:
    if camera_id not in cameras:
        cam_cfg = config.get("camera", {})
        alert_cfg = config.get("alert", {})
        screenshot_cfg = alert_cfg.get("screenshot", {})

        # 分辨率配置：auto_resolution=true 时使用 None（自动获取）
        auto_resolution = cam_cfg.get("auto_resolution", True)
        width = None if auto_resolution else cam_cfg.get("width")
        height = None if auto_resolution else cam_cfg.get("height")

        cameras[camera_id] = CameraManager(
            camera_id=camera_id,
            width=width,
            height=height,
            signal_callback=_camera_signal_callback,
            db_manager=db_manager,
            redis_stats=redis_stats,
            screenshot_config=screenshot_cfg,
        )

        # 应用检测配置
        det_cfg = config.get("detection", {})
        if det_cfg.get("conf_threshold") is not None:
            cameras[camera_id].conf_threshold = float(det_cfg["conf_threshold"])
        if det_cfg.get("detect_every_n") is not None:
            cameras[camera_id].detect_every_n = int(det_cfg["detect_every_n"])

        # 应用告警配置
        if alert_cfg.get("cooldown_sec") is not None:
            cameras[camera_id]._alert_cooldown_sec = float(alert_cfg["cooldown_sec"])
        if alert_cfg.get("track_ttl_sec") is not None:
            cameras[camera_id]._track_ttl_sec = float(alert_cfg["track_ttl_sec"])

        cameras[camera_id].start()

        # Redis 标记摄像头在线
        if redis_stats and redis_stats.is_enabled():
            redis_stats.set_camera_online(camera_id)

        entry = structured_logger.log("info", "camera.created", "摄像头实例已创建", camera_id=camera_id)
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
                await websocket.send_json({"type": "pong", "timestamp": structured_logger._iso_now()})
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
async def get_logs(limit: int = 100):
    logs = structured_logger.get_recent_logs(limit)
    return {"count": len(logs), "logs": logs}


# ------------------------------------------------------------------ #
#  健康检查
# ------------------------------------------------------------------ #

@app.get("/health")
async def health():
    camera_stats = [cam.get_status() for cam in cameras.values()]
    # 任意摄像头断线或模型未加载则降级
    all_ok = all(s["connected"] and s["model_loaded"] for s in camera_stats) if camera_stats else True
    status = "ok" if all_ok else "degraded"
    return {
        "status": status,
        "timestamp": structured_logger._iso_now(),
        "uptime_sec": int(time.time() - START_TS),
        "ws_clients": len(_ws_clients),
        "camera_count": len(cameras),
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
):
    """查询告警历史记录"""
    if not db_manager:
        raise HTTPException(status_code=503, detail="数据库未配置")

    try:
        # 解析时间参数
        start_dt = datetime.fromisoformat(start_time) if start_time else None
        end_dt = datetime.fromisoformat(end_time) if end_time else None

        result = db_manager.query_alerts(
            limit=limit,
            offset=offset,
            camera_id=camera_id,
            start_time=start_dt,
            end_time=end_dt,
            level=level,
        )
        result["limit"] = limit
        result["offset"] = offset
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"查询失败: {str(e)}")


@app.get("/api/alerts/{alert_id}/screenshot")
async def get_alert_screenshot(alert_id: int):
    """获取告警截图"""
    if not db_manager:
        raise HTTPException(status_code=503, detail="数据库未配置")

    try:
        alert = db_manager.get_alert_by_id(alert_id)
        if not alert or not alert.screenshot_path:
            raise HTTPException(status_code=404, detail="截图不存在")

        screenshot_file = ROOT / "screenshots" / alert.screenshot_path
        if not screenshot_file.exists():
            raise HTTPException(status_code=404, detail="截图文件已删除")

        return FileResponse(screenshot_file, media_type="image/jpeg")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取截图失败: {str(e)}")


# ------------------------------------------------------------------ #
#  实时统计数据
# ------------------------------------------------------------------ #

@app.get("/api/stats")
async def get_stats():
    """获取 Redis 实时统计数据"""
    if not redis_stats or not redis_stats.is_enabled():
        return JSONResponse(
            status_code=503,
            content={"error": "Redis 统计功能未启用"}
        )

    try:
        return redis_stats.get_all_stats()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取统计数据失败: {str(e)}")


# ------------------------------------------------------------------ #
#  前端页面
# ------------------------------------------------------------------ #

FRONTEND = Path(__file__).parent.parent / "frontend"


@app.get("/", response_class=HTMLResponse)
async def root():
    return HTMLResponse((FRONTEND / "index.html").read_text(encoding="utf-8"))


if __name__ == "__main__":
    import logging
    # 屏蔽 uvicorn 的 "Uvicorn running on http://0.0.0.0:8000" 误导性输出
    logging.getLogger("uvicorn.error").setLevel(logging.WARNING)
    print("启动监控服务器 -> http://localhost:8000")
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=False)
