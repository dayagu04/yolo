from fastapi import FastAPI, Request, Response
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
import uvicorn
import cv2
from pathlib import Path
import sys
sys.path.append(str(Path(__file__).parent.parent))

from server.camera import CameraManager

app = FastAPI(title="实时视频监控服务器")

# 全局摄像头管理器 (支持多个摄像头)
cameras = {}

def get_camera(camera_id: int = 0):
    if camera_id not in cameras:
        cameras[camera_id] = CameraManager(camera_id=camera_id)
        cameras[camera_id].start()
    return cameras[camera_id]

@app.get("/", response_class=HTMLResponse)
async def root():
    """返回监控页面"""
    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>实时视频监控</title>
        <style>
            body { font-family: Arial; text-align: center; background: #f0f0f0; margin: 0; padding: 20px; }
            .container { max-width: 800px; margin: 0 auto; }
            video, img { width: 100%; max-width: 800px; border: 2px solid #333; border-radius: 8px; }
            h1 { color: #333; }
            .status { color: green; font-weight: bold; }
            button { padding: 10px 20px; margin: 10px; font-size: 16px; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>📹 实时视频监控系统</h1>
            <p class="status">✅ 连接中...</p>
            <img id="video" src="/video_feed" alt="视频流">
            <br>
            <button onclick="location.reload()">刷新画面</button>
            <p>支持后续集成YOLO目标检测和多摄像头</p>
        </div>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)

@app.get("/video_feed")
async def video_feed(camera_id: int = 0):
    """MJPEG视频流"""
    camera = get_camera(camera_id)
    return StreamingResponse(
        camera.get_frame_generator(),
        media_type="multipart/x-mixed-replace; boundary=frame"
    )

@app.get("/health")
async def health():
    return {"status": "healthy", "cameras": len(cameras)}

if __name__ == "__main__":
    print("启动实时监控服务器...")
    print("访问 http://localhost:8000 查看监控画面")
    uvicorn.run(app, host="0.0.0.0", port=8000)
