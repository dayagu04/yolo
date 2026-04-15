import cv2
import threading
import time
from pathlib import Path
from typing import Optional, Generator, Callable
import numpy as np

MODEL_PATH = Path(__file__).parent.parent / "models" / "person_best.pt"


class CameraManager:
    def __init__(
        self,
        camera_id: int = 0,
        width: int = 640,
        height: int = 480,
        alert_callback: Optional[Callable] = None,
    ):
        self.camera_id = camera_id
        self.width = width
        self.height = height
        self.alert_callback = alert_callback

        self.cap: Optional[cv2.VideoCapture] = None
        self.frame = None
        self.running = False
        self.lock = threading.Lock()
        self.thread = None

        # YOLO 检测状态
        self.detection_enabled = True
        self.conf_threshold = 0.5
        self.detect_every_n = 2          # 每 N 帧检测一次（性能优化）
        self._frame_count = 0
        self._last_results = None        # 缓存上次检测结果
        self._last_alert_time = 0.0

        # 延迟加载模型（避免导入时崩溃）
        self._model = None

    def _load_model(self):
        if self._model is not None:
            return
        try:
            from ultralytics import YOLO
            self._model = YOLO(str(MODEL_PATH))
            print(f"YOLO 模型已加载: {MODEL_PATH}")
        except Exception as e:
            print(f"YOLO 模型加载失败: {e}")
            self._model = None

    # ------------------------------------------------------------------ #
    #  摄像头生命周期
    # ------------------------------------------------------------------ #

    def start(self):
        if self.running:
            return
        self._load_model()
        self.cap = cv2.VideoCapture(self.camera_id)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        self.running = True
        self.thread = threading.Thread(target=self._capture_loop, daemon=True)
        self.thread.start()
        print(f"摄像头 {self.camera_id} 已启动")

    def stop(self):
        self.running = False
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=1)
        if self.cap:
            self.cap.release()
        print(f"摄像头 {self.camera_id} 已停止")

    # ------------------------------------------------------------------ #
    #  帧捕获（后台线程）
    # ------------------------------------------------------------------ #

    def _capture_loop(self):
        while self.running and self.cap and self.cap.isOpened():
            ret, frame = self.cap.read()
            if ret:
                frame = cv2.resize(frame, (self.width, self.height))
                with self.lock:
                    self.frame = frame.copy()
            else:
                time.sleep(0.1)

    def get_frame(self) -> Optional[np.ndarray]:
        with self.lock:
            return self.frame.copy() if self.frame is not None else None

    # ------------------------------------------------------------------ #
    #  YOLO 检测
    # ------------------------------------------------------------------ #

    def _detect(self, frame: np.ndarray):
        """在 frame 上运行 YOLO，返回标注后的帧和检测到的人数。"""
        if self._model is None:
            return frame, 0

        results = self._model(frame, verbose=False, conf=self.conf_threshold)
        self._last_results = results

        person_count = len(results[0].boxes)

        # 触发告警（5 秒防抖）
        if person_count > 0 and self.alert_callback:
            now = time.time()
            if now - self._last_alert_time > 5:
                self._last_alert_time = now
                self.alert_callback({
                    "type": "person_detected",
                    "count": person_count,
                    "timestamp": now,
                })

        annotated = results[0].plot()
        return annotated, person_count

    # ------------------------------------------------------------------ #
    #  MJPEG 流生成器
    # ------------------------------------------------------------------ #

    def get_frame_generator(self) -> Generator[bytes, None, None]:
        while self.running:
            frame = self.get_frame()
            if frame is None:
                time.sleep(0.033)
                continue

            self._frame_count += 1

            if self.detection_enabled and self._model is not None:
                if self._frame_count % self.detect_every_n == 0:
                    output_frame, _ = self._detect(frame)
                elif self._last_results is not None:
                    # 复用上次检测框（避免闪烁）
                    output_frame = self._last_results[0].plot()
                else:
                    output_frame = frame
            else:
                output_frame = frame

            ret, jpeg = cv2.imencode(
                ".jpg", output_frame, [cv2.IMWRITE_JPEG_QUALITY, 85]
            )
            if ret:
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n\r\n"
                    + jpeg.tobytes()
                    + b"\r\n"
                )

            time.sleep(0.033)  # ~30 fps

    # ------------------------------------------------------------------ #
    #  运行时配置（供 API 调用）
    # ------------------------------------------------------------------ #

    def set_conf(self, conf: float):
        self.conf_threshold = max(0.1, min(0.95, conf))

    def toggle_detection(self, enabled: bool):
        self.detection_enabled = enabled

    def get_status(self) -> dict:
        return {
            "camera_id": self.camera_id,
            "running": self.running,
            "detection_enabled": self.detection_enabled,
            "conf_threshold": self.conf_threshold,
            "model_loaded": self._model is not None,
        }
