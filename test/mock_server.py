#!/usr/bin/env python3
"""
前端 UI 预览测试服务器（Mock Backend）
用于独立测试前端界面，无需真实摄像头和 YOLO 模型

启动方式：
  python test/mock_server.py

访问地址：
  http://localhost:8000
"""
import asyncio
import json
import random
import time
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, Response
import uvicorn

app = FastAPI(title="Mock 监控服务器")

START_TS = time.time()
_ws_clients: list[WebSocket] = []
_alert_count = 0
_person_count = 0
_mock_logs = []


def _iso_now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


# ------------------------------------------------------------------ #
#  Mock 视频流（静态图片循环）
# ------------------------------------------------------------------ #

@app.get("/video_feed")
async def video_feed(camera_id: int = 0):
    """返回一个简单的 MJPEG 流（纯色帧 + 文字）"""
    async def generate():
        import io
        try:
            from PIL import Image, ImageDraw, ImageFont
            has_pil = True
        except ImportError:
            has_pil = False

        frame_num = 0
        while True:
            if has_pil:
                img = Image.new('RGB', (640, 480), color=(20, 20, 30))
                draw = ImageDraw.Draw(img)
                draw.text((250, 220), f"MOCK STREAM", fill=(0, 229, 255))
                draw.text((260, 250), f"Frame {frame_num}", fill=(150, 150, 150))
                buf = io.BytesIO()
                img.save(buf, format='JPEG', quality=80)
                jpeg_bytes = buf.getvalue()
            else:
                # 无 PIL 时返回最小 JPEG（1x1 黑色像素）
                jpeg_bytes = bytes.fromhex(
                    'ffd8ffe000104a46494600010100000100010000ffdb004300080606070605080707'
                    '07090909080a0c140d0c0b0b0c1912130f141d1a1f1e1d1a1c1c20242e2720222c'
                    '231c1c2837292c30313434341f27393d38323c2e333432ffdb0043010909090c0b'
                    '0c180d0d1832211c213232323232323232323232323232323232323232323232323232'
                    '32323232323232323232323232323232323232323232ffc00011080001000103012200'
                    '021101031101ffc4001500010100000000000000000000000000000000ffc400140001'
                    '0000000000000000000000000000000000ffda000c03010002110311003f00bf800ffd9'
                )

            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n\r\n"
                + jpeg_bytes
                + b"\r\n"
            )
            frame_num += 1
            await asyncio.sleep(0.05)  # ~20 fps

    return Response(generate(), media_type="multipart/x-mixed-replace; boundary=frame")


# ------------------------------------------------------------------ #
#  WebSocket 模拟告警与日志推送
# ------------------------------------------------------------------ #

async def _broadcast(msg: dict):
    dead = []
    for ws in _ws_clients:
        try:
            await ws.send_json(msg)
        except Exception:
            dead.append(ws)
    for ws in dead:
        if ws in _ws_clients:
            _ws_clients.remove(ws)


async def _mock_event_generator():
    """后台任务：随机生成告警和日志事件"""
    global _alert_count, _person_count
    await asyncio.sleep(3)  # 启动后 3 秒开始

    while True:
        await asyncio.sleep(random.uniform(8, 20))

        # 随机生成人数变化
        _person_count = random.choice([0, 0, 0, 1, 1, 2, 3])

        if _person_count > 0 and random.random() < 0.6:
            # 60% 概率触发告警
            _alert_count += 1
            alert_msg = {
                "type": "alert",
                "timestamp": _iso_now(),
                "level": "high",
                "message": f"检测到 {_person_count} 名新出现人员",
                "camera_id": 0,
                "data": {
                    "person_count": _person_count,
                    "new_track_ids": [random.randint(10, 99)],
                    "active_tracks": _person_count,
                },
            }
            await _broadcast(alert_msg)
            _mock_logs.append(alert_msg)

        # 随机日志
        if random.random() < 0.3:
            log_msg = {
                "type": "log",
                "timestamp": _iso_now(),
                "level": random.choice(["info", "info", "warning"]),
                "event": random.choice(["camera.frame_ok", "model.inference", "track.update"]),
                "message": random.choice([
                    "摄像头帧读取正常",
                    "YOLO 推理完成",
                    "Track 状态更新",
                    "检测配置已应用",
                ]),
                "camera_id": 0,
                "data": {},
            }
            await _broadcast(log_msg)
            _mock_logs.append(log_msg)
            if len(_mock_logs) > 200:
                _mock_logs.pop(0)


@app.on_event("startup")
async def on_startup():
    asyncio.create_task(_mock_event_generator())


@app.websocket("/ws/alert")
async def websocket_alert(websocket: WebSocket):
    await websocket.accept()
    _ws_clients.append(websocket)
    print(f"[WS] 客户端连接，当前 {len(_ws_clients)} 个")

    try:
        while True:
            payload = await websocket.receive_text()
            if payload == "ping":
                await websocket.send_json({"type": "pong", "timestamp": _iso_now()})
    except WebSocketDisconnect:
        pass
    finally:
        if websocket in _ws_clients:
            _ws_clients.remove(websocket)
        print(f"[WS] 客户端断开，剩余 {len(_ws_clients)} 个")


# ------------------------------------------------------------------ #
#  API Mock
# ------------------------------------------------------------------ #

@app.post("/api/camera/{camera_id}/config")
async def update_config(camera_id: int, cfg: dict):
    print(f"[API] 配置更新: {cfg}")
    return {
        "camera_id": camera_id,
        "running": True,
        "connected": True,
        "detection_enabled": cfg.get("enabled", True),
        "conf_threshold": cfg.get("conf", 0.5),
        "model_loaded": True,
        "fps": 28.5,
        "last_frame_age_ms": 35,
        "reconnect_attempts": 0,
        "active_tracks": _person_count,
        "alert_total": _alert_count,
    }


@app.get("/api/camera/{camera_id}/status")
async def camera_status(camera_id: int):
    return {
        "camera_id": camera_id,
        "running": True,
        "connected": True,
        "detection_enabled": True,
        "conf_threshold": 0.5,
        "model_loaded": True,
        "fps": round(random.uniform(27, 30), 1),
        "last_frame_age_ms": random.randint(30, 50),
        "reconnect_attempts": 0,
        "active_tracks": _person_count,
        "alert_total": _alert_count,
    }


@app.get("/api/logs")
async def get_logs(limit: int = 100):
    logs = _mock_logs[-limit:]
    return {"count": len(logs), "logs": logs}


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "timestamp": _iso_now(),
        "uptime_sec": int(time.time() - START_TS),
        "ws_clients": len(_ws_clients),
        "camera_count": 1,
        "cameras": [
            {
                "camera_id": 0,
                "running": True,
                "connected": True,
                "model_loaded": True,
                "detection_enabled": True,
                "conf_threshold": 0.5,
                "fps": round(random.uniform(27, 30), 1),
                "last_frame_age_ms": random.randint(30, 50),
                "reconnect_attempts": 0,
                "active_tracks": _person_count,
                "alert_total": _alert_count,
            }
        ],
    }


# ------------------------------------------------------------------ #
#  前端页面
# ------------------------------------------------------------------ #

FRONTEND = Path(__file__).parent.parent / "frontend"


@app.get("/", response_class=HTMLResponse)
async def root():
    html_path = FRONTEND / "index.html"
    if not html_path.exists():
        return HTMLResponse("<h1>前端文件未找到</h1><p>请确保 frontend/index.html 存在</p>", status_code=404)
    return HTMLResponse(html_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    print("=" * 60)
    print("  Mock 监控服务器（前端预览测试）")
    print("=" * 60)
    print("  访问地址: http://localhost:8000")
    print("  功能说明:")
    print("    - 模拟视频流（纯色帧）")
    print("    - 随机生成告警与日志事件")
    print("    - 支持所有前端 API 调用")
    print("=" * 60)
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="warning")
