import cv2
import threading
import time
from typing import Optional, Generator
import numpy as np

class CameraManager:
    def __init__(self, camera_id: int = 0, width: int = 640, height: int = 480):
        self.camera_id = camera_id
        self.width = width
        self.height = height
        self.cap: Optional[cv2.VideoCapture] = None
        self.frame = None
        self.running = False
        self.lock = threading.Lock()
        self.thread = None
    
    def start(self):
        """启动摄像头捕获线程"""
        if self.running:
            return
        self.cap = cv2.VideoCapture(self.camera_id)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        self.running = True
        self.thread = threading.Thread(target=self._capture_loop, daemon=True)
        self.thread.start()
        print(f"摄像头 {self.camera_id} 已启动")
    
    def _capture_loop(self):
        """持续捕获帧"""
        while self.running and self.cap and self.cap.isOpened():
            ret, frame = self.cap.read()
            if ret:
                frame = cv2.resize(frame, (self.width, self.height))
                with self.lock:
                    self.frame = frame.copy()
            else:
                time.sleep(0.1)
    
    def get_frame(self) -> Optional[np.ndarray]:
        """获取最新帧"""
        with self.lock:
            return self.frame.copy() if self.frame is not None else None
    
    def get_frame_generator(self) -> Generator[bytes, None, None]:
        """生成MJPEG流"""
        while self.running:
            frame = self.get_frame()
            if frame is not None:
                # 可在此处插入YOLO检测
                ret, jpeg = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
                if ret:
                    yield (b'--frame\r\n'
                           b'Content-Type: image/jpeg\r\n\r\n' + jpeg.tobytes() + b'\r\n')
            time.sleep(0.033)  # ~30fps
    
    def stop(self):
        """停止摄像头"""
        self.running = False
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=1)
        if self.cap:
            self.cap.release()
        print(f"摄像头 {self.camera_id} 已停止")
