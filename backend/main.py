import asyncio
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).parent.parent))

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel
import uvicorn

from backend.camera import CameraManager

app = FastAPI(title="智能视频监控")

# ------------------------------------------------------------------ #
#  摄像头管理
# ------------------------------------------------------------------ #

cameras: dict = {}


def get_camera(camera_id: int = 0) -> CameraManager:
    if camera_id not in cameras:
        cameras[camera_id] = CameraManager(
            camera_id=camera_id,
            alert_callback=lambda msg: asyncio.create_task(_broadcast(msg)),
        )
        cameras[camera_id].start()
    return cameras[camera_id]


# ------------------------------------------------------------------ #
#  WebSocket 连接池
# ------------------------------------------------------------------ #

_ws_clients: list = []


async def _broadcast(message: dict):
    dead = []
    for ws in _ws_clients:
        try:
            await ws.send_json(message)
        except Exception:
            dead.append(ws)
    for ws in dead:
        _ws_clients.remove(ws)


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    _ws_clients.append(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        if websocket in _ws_clients:
            _ws_clients.remove(websocket)


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
#  控制 API
# ------------------------------------------------------------------ #

class DetectionConfig(BaseModel):
    enabled: bool = None
    conf: float = None


@app.post("/api/camera/{camera_id}/config")
async def update_config(camera_id: int, cfg: DetectionConfig):
    camera = get_camera(camera_id)
    if cfg.enabled is not None:
        camera.toggle_detection(cfg.enabled)
    if cfg.conf is not None:
        camera.set_conf(cfg.conf)
    return camera.get_status()


@app.get("/api/camera/{camera_id}/status")
async def camera_status(camera_id: int):
    return get_camera(camera_id).get_status()


@app.get("/health")
async def health():
    return {"status": "ok", "cameras": len(cameras), "ws_clients": len(_ws_clients)}


# ------------------------------------------------------------------ #
#  前端页面
# ------------------------------------------------------------------ #

FRONTEND = Path(__file__).parent.parent / "frontend"


@app.get("/", response_class=HTMLResponse)
async def root():
    return HTMLResponse((FRONTEND / "index.html").read_text(encoding="utf-8"))


if __name__ == "__main__":
    print("启动监控服务器 → http://localhost:8000")
    uvicorn.run(app, host="0.0.0.0", port=8000)
