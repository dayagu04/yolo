import asyncio
import sys
import time
from pathlib import Path
from typing import Optional

# 确保项目根目录在 sys.path 中
ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, StreamingResponse
import uvicorn

from backend.camera import CameraManager
from backend.logging_system import structured_logger
from backend.schemas import DetectionConfig

app = FastAPI(title="智能视频监控")

# ------------------------------------------------------------------ #
#  全局状态
# ------------------------------------------------------------------ #

START_TS = time.time()
cameras: dict[int, CameraManager] = {}
_ws_clients: list[WebSocket] = []
_event_loop: Optional[asyncio.AbstractEventLoop] = None


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
    global _event_loop
    _event_loop = asyncio.get_running_loop()
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
        cameras[camera_id] = CameraManager(
            camera_id=camera_id,
            signal_callback=_camera_signal_callback,
        )
        cameras[camera_id].start()
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
