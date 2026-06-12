"""
摄像头管理器 - 重构为组合模式

职责：协调 VideoCapture、ObjectDetector、AlertManager 三个子系统，
      主循环只负责流程编排，不包含具体实现细节。
"""
import collections
import sys
import threading
import time
from pathlib import Path
from typing import Callable, Generator, Optional, Union

import cv2
import numpy as np

ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.detection import ObjectDetector
from backend.video_capture import VideoCapture
from backend.alert_manager import AlertManager
from backend.roi_detector import ROIDetector
from backend.screenshot import ScreenshotManager
from backend.tracker import PersonTracker

MODEL_PATH = Path(__file__).parent.parent / "models" / "person_best.pt"


class CameraManager:
    """
    摄像头管理器（协调器）

    组合三个子系统：
    - VideoCapture: 视频流采集和连接管理
    - ObjectDetector: YOLO 推理和缓存（修复 M6）
    - AlertManager: 告警生成和异常感知（修复 M5）

    主循环职责：
    1. 从 VideoCapture 读帧
    2. 交给 ObjectDetector 推理
    3. 将结果交给 AlertManager 处理告警
    4. 更新帧缓冲和 FPS
    """

    def __init__(
        self,
        camera_id: int = 0,
        source: Union[int, str] = 0,
        width: Optional[int] = None,
        height: Optional[int] = None,
        device: str = "cpu",
        signal_callback: Optional[Callable[[dict], None]] = None,
        db_manager=None,
        redis_stats=None,
        screenshot_config: Optional[dict] = None,
    ):
        self.camera_id = camera_id
        self.source = source if source is not None else camera_id
        self.signal_callback = signal_callback
        self.db_manager = db_manager
        self.redis_stats = redis_stats

        # ── 子系统组装 ──
        self.video_capture = VideoCapture(
            source=self.source,
            width=width,
            height=height,
        )

        self.detector = ObjectDetector(
            model_path=str(MODEL_PATH),
            device=device,
            conf_threshold=0.5,
            cache_enabled=True,
        )

        self.tracker = PersonTracker()

        self.screenshot_mgr = ScreenshotManager(
            camera_id=camera_id,
            config=screenshot_config or {},
            root_path=ROOT,
            emit_log=self._emit_log,
        )

        self.alert_manager = AlertManager(
            camera_id=camera_id,
            tracker=self.tracker,
            screenshot_manager=self.screenshot_mgr,
            signal_callback=signal_callback,
            cooldown_sec=5.0,
        )

        self.roi_detector = ROIDetector(db_manager=db_manager)

        # ── 运行时状态 ──
        self.running = False
        self.thread = None
        self.lock = threading.Lock()

        # 当前帧（供 MJPEG 流读取）
        self.frame: Optional[np.ndarray] = None
        self.last_frame_ts: float = 0.0

        # FPS 统计
        self._fps: float = 0.0
        self._last_fps_ts: float = 0.0

        # 检测控制
        self.detection_enabled = True
        self.detect_every_n = 2
        self._frame_count = 0

        # 帧缓冲（录像回放，保留最近 300 帧 ≈ 10s @30fps）
        self._frame_buffer: collections.deque = collections.deque(maxlen=300)
        self._buffer_lock = threading.Lock()

        # 属性别名（兼容旧代码）
        self._alert_cooldown_sec = 5.0
        self._track_ttl_sec = 30.0

    # ------------------------------------------------------------------ #
    #  属性访问器（兼容旧接口）
    # ------------------------------------------------------------------ #

    @property
    def conf_threshold(self) -> float:
        return self.detector.conf_threshold

    @conf_threshold.setter
    def conf_threshold(self, value: float):
        self.detector.set_conf_threshold(value)

    @property
    def _alert_cooldown_sec(self) -> float:
        return self.alert_manager.cooldown_sec

    @_alert_cooldown_sec.setter
    def _alert_cooldown_sec(self, value: float):
        self.alert_manager.cooldown_sec = value

    @property
    def _track_ttl_sec(self) -> float:
        return self.tracker.ttl_sec

    @_track_ttl_sec.setter
    def _track_ttl_sec(self, value: float):
        self.tracker.ttl_sec = value

    @property
    def connected(self) -> bool:
        return self.video_capture.is_connected()

    # ------------------------------------------------------------------ #
    #  生命周期管理
    # ------------------------------------------------------------------ #

    def start(self):
        """启动采集线程"""
        if self.running:
            return

        # 加载模型
        if not self.detector.is_loaded():
            success = self.detector.load_model()
            if not success:
                self._emit_log("error", "model.load_failed",
                              f"模型加载失败: {self.detector.get_last_error()}")
                return

        self.running = True
        self.thread = threading.Thread(target=self._capture_loop, daemon=True)
        self.thread.start()
        self._emit_log("info", "camera.started", f"摄像头 {self.camera_id} 已启动")

    def stop(self):
        """停止采集线程"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=2.0)
        self.video_capture.close()
        self._emit_log("info", "camera.stopped", f"摄像头 {self.camera_id} 已停止")

    # ------------------------------------------------------------------ #
    #  主循环（协调三个子系统）
    # ------------------------------------------------------------------ #

    def _capture_loop(self):
        """主采集循环（线程入口）"""
        self._last_fps_ts = time.time()

        while self.running:
            # 1. 读帧
            ret, raw_frame = self.video_capture.read_frame()

            if not ret or raw_frame is None:
                time.sleep(0.1)
                continue

            self._frame_count += 1
            frame_ts = time.time()

            # 2. 推理（M6 修复在 ObjectDetector 内部）
            annotated_frame, person_count, results, error = self.detector.detect(
                raw_frame, self.detect_every_n, self._frame_count
            )

            # 3. 告警处理（M5 修复：error 传入 AlertManager）
            if self.detection_enabled:
                self.alert_manager.process_detections(
                    raw_frame, results, person_count, error, frame_ts
                )

            # 4. 更新帧缓冲（线程安全）
            with self._buffer_lock:
                self._frame_buffer.append((frame_ts, annotated_frame.copy()))

            # 5. 更新当前帧（供 MJPEG 流读取）
            with self.lock:
                self.frame = annotated_frame
                self.last_frame_ts = frame_ts

            # 6. 更新 FPS
            self._update_fps(frame_ts)

            # 7. Redis 统计
            if self.redis_stats and results is not None:
                try:
                    self.redis_stats.update_camera_stats(
                        self.camera_id,
                        person_count=person_count,
                        active_tracks=self.tracker.active_count(),
                    )
                except Exception:
                    pass

            time.sleep(0.01)  # 控制循环频率

    def _update_fps(self, now: float):
        """更新 FPS 统计"""
        elapsed = now - self._last_fps_ts
        if elapsed >= 1.0:
            self._fps = self._frame_count / elapsed
            self._frame_count = 0
            self._last_fps_ts = now

    # ------------------------------------------------------------------ #
    #  帧获取（MJPEG 流）
    # ------------------------------------------------------------------ #

    def get_frame(self) -> Optional[np.ndarray]:
        """获取当前帧（线程安全）"""
        with self.lock:
            return self.frame.copy() if self.frame is not None else None

    def get_frame_buffer(self, seconds: float = 10.0) -> list[tuple]:
        """获取最近 N 秒的帧缓冲（用于录像回放）"""
        cutoff = time.time() - seconds
        with self._buffer_lock:
            return [(ts, f.copy()) for ts, f in self._frame_buffer if ts >= cutoff]

    def get_frame_generator(self) -> Generator[bytes, None, None]:
        """MJPEG 流生成器（供 /video_feed 端点）"""
        last_encode_ts = time.time()
        encode_interval = 0.033  # ~30fps

        while True:
            frame = self.get_frame()
            now = time.time()

            if frame is None or (now - last_encode_ts) < encode_interval:
                time.sleep(0.01)
                continue

            try:
                ret, jpeg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
                if ret:
                    yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" +
                           jpeg.tobytes() + b"\r\n")
                    last_encode_ts = now
            except Exception:
                time.sleep(0.1)

    # ------------------------------------------------------------------ #
    #  控制接口
    # ------------------------------------------------------------------ #

    def toggle_detection(self, enabled: bool):
        """切换检测开关"""
        self.detection_enabled = enabled
        self._emit_log("info", "detection.toggled",
                      f"检测已{'启用' if enabled else '禁用'}")

    def set_conf(self, conf: float):
        """设置置信度阈值"""
        self.detector.set_conf_threshold(conf)
        self._emit_log("info", "conf.updated", f"置信度阈值已更新: {conf}")

    def reload_model(self, model_path: Optional[str] = None):
        """重新加载模型"""
        success = self.detector.reload_model(model_path)
        if success:
            self._emit_log("info", "model.reloaded", "模型已重新加载")
        else:
            self._emit_log("error", "model.reload_failed",
                          f"模型重载失败: {self.detector.get_last_error()}")

    # ------------------------------------------------------------------ #
    #  状态查询
    # ------------------------------------------------------------------ #

    def get_status(self) -> dict:
        """获取状态摘要"""
        w, h = self.video_capture.get_resolution()
        return {
            "camera_id": self.camera_id,
            "connected": self.connected,
            "running": self.running,
            "detection_enabled": self.detection_enabled,
            "model_loaded": self.detector.is_loaded(),
            "fps": round(self._fps, 2),
            "resolution": f"{w}x{h}",
            "active_tracks": self.tracker.active_count,
            "alert_total": self.alert_manager.get_alert_count(),
            "conf_threshold": self.conf_threshold,
        }

    # ------------------------------------------------------------------ #
    #  信号发送（日志/告警）
    # ------------------------------------------------------------------ #

    def _emit_log(self, level: str, event: str, message: str, data: Optional[dict] = None):
        """发送日志信号"""
        if self.signal_callback:
            self.signal_callback({
                "type": "log",
                "level": level,
                "event": event,
                "camera_id": self.camera_id,
                "message": message,
                "data": data or {},
            })

    @staticmethod
    def _now_iso() -> str:
        from datetime import datetime
        return datetime.now().isoformat()
