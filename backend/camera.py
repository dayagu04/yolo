import cv2
import sys
import threading
import time
import collections
from datetime import datetime
from pathlib import Path
from typing import Optional, Generator, Callable, Union

import numpy as np

ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.schemas import AlertMessage, StatusMessage, LogMessage
from backend.tracker import PersonTracker
from backend.screenshot import ScreenshotManager
from backend.roi_detector import ROIDetector

MODEL_PATH = Path(__file__).parent.parent / "models" / "person_best.pt"


class CameraManager:
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
        self.width = width
        self.height = height
        self.device = device
        self.signal_callback = signal_callback
        self.db_manager = db_manager
        self.redis_stats = redis_stats

        # 子组件：轨迹管理 + 截图管理 + ROI 检测
        self.tracker = PersonTracker()
        self.screenshot_mgr = ScreenshotManager(
            camera_id=camera_id,
            config=screenshot_config or {},
            root_path=ROOT,
            emit_log=self._emit_log,
        )
        self.roi_detector = ROIDetector(db_manager=db_manager)

        # 摄像头 I/O 状态
        self.cap: Optional[cv2.VideoCapture] = None
        self.frame = None
        self.running = False
        self.connected = False
        self.lock = threading.Lock()
        self.thread = None
        self.last_frame_ts: float = 0.0
        self._last_fps_ts: float = 0.0
        self._fps: float = 0.0
        self._reconnect_attempts = 0

        # 检测状态
        self.detection_enabled = True
        self.conf_threshold = 0.5
        self.detect_every_n = 2
        self._frame_count = 0
        self._last_results = None
        self._alert_total = 0
        self._model = None

        # 帧缓冲（用于录像回放，保留最近 300 帧 ≈ 10 秒 @30fps）
        self._frame_buffer: collections.deque = collections.deque(maxlen=300)
        self._buffer_lock = threading.Lock()

        # 自适应跳帧
        self._adaptive_skip = True
        self._base_detect_every_n = 2
        self._prev_gray: Optional[np.ndarray] = None
        self._scene_change_threshold = 5.0  # 帧差均值阈值

        # 推理缓存
        self._inference_cache_enabled = True
        self._last_inference_ts: float = 0.0
        self._cache_max_age_sec: float = 0.5  # 缓存最大有效期

    # 向后兼容属性：main.py 直接赋值这两个字段
    @property
    def _alert_cooldown_sec(self) -> float:
        return self.tracker.alert_cooldown_sec

    @_alert_cooldown_sec.setter
    def _alert_cooldown_sec(self, value: float):
        self.tracker.alert_cooldown_sec = value

    @property
    def _track_ttl_sec(self) -> float:
        return self.tracker.track_ttl_sec

    @_track_ttl_sec.setter
    def _track_ttl_sec(self, value: float):
        self.tracker.track_ttl_sec = value

    @staticmethod
    def _now_iso() -> str:
        return datetime.now().astimezone().isoformat(timespec="seconds")

    def _emit(self, payload: dict):
        if self.signal_callback:
            self.signal_callback(payload)

    def _emit_log(self, level: str, event: str, message: str, data: Optional[dict] = None):
        self._emit(
            LogMessage(
                timestamp=self._now_iso(),
                level=level,
                event=event,
                message=message,
                camera_id=self.camera_id,
                data=data or {},
            ).model_dump()
        )

    def _emit_status(self, level: str, message: str, data: Optional[dict] = None):
        self._emit(
            StatusMessage(
                timestamp=self._now_iso(),
                level=level,
                message=message,
                camera_id=self.camera_id,
                data=data or {},
            ).model_dump()
        )

    def _load_model(self):
        if self._model is not None:
            return
        try:
            from ultralytics import YOLO
            self._model = YOLO(str(MODEL_PATH))
            if self.device != "cpu":
                self._model.to(self.device)
                self._emit_log("info", "model.loaded",
                               f"YOLO 模型已加载: {MODEL_PATH} (device={self.device})")
            else:
                self._emit_log("info", "model.loaded", f"YOLO 模型已加载: {MODEL_PATH}")
        except Exception as e:
            self._model = None
            self._emit_log("error", "model.load_failed", f"YOLO 模型加载失败: {e}")

    def reload_model(self, model_path: Optional[str] = None):
        """热加载模型权重（不停止摄像头线程）"""
        old_model = self._model
        self._model = None
        try:
            from ultralytics import YOLO
            path = model_path or str(MODEL_PATH)
            self._model = YOLO(path)
            if self.device != "cpu":
                self._model.to(self.device)
            self._emit_log("info", "model.reloaded", f"模型热加载成功: {path}")
            return True
        except Exception as e:
            self._model = old_model  # 回滚到旧模型
            self._emit_log("error", "model.reload_failed", f"模型热加载失败: {e}")
            return False

    # ------------------------------------------------------------------ #
    #  摄像头生命周期
    # ------------------------------------------------------------------ #

    def _open_camera(self) -> bool:
        source = self.source
        is_rtsp = isinstance(source, str) and source.lower().startswith("rtsp")
        cap = (cv2.VideoCapture(source) if is_rtsp
               else cv2.VideoCapture(int(source), cv2.CAP_DSHOW))

        if not cap.isOpened():
            cap.release()
            return False

        if self.width is not None:
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        if self.height is not None:
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)

        actual_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        actual_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

        for _ in range(5):  # 丢弃 DSHOW 曝光预热黑帧
            cap.read()

        self.width, self.height = actual_w, actual_h
        self.cap = cap
        self.connected = True
        self._reconnect_attempts = 0
        self._emit_status(
            "info",
            f"摄像头已连接 ({actual_w}x{actual_h})",
            {"camera_connected": True, "model_loaded": self._model is not None,
             "resolution": f"{actual_w}x{actual_h}"},
        )
        return True

    def _close_camera(self):
        if self.cap:
            self.cap.release()
        self.cap = None
        self.connected = False

    def _ensure_camera_connected(self) -> bool:
        max_attempts = 20
        max_delay = 60  # 最大退避间隔（秒）
        base_delay = 1  # 初始退避间隔（秒）

        for attempt in range(1, max_attempts + 1):
            if not self.running:
                return False
            self._reconnect_attempts = attempt
            if self._open_camera():
                if attempt > 1:
                    self._emit_log("info", "camera.reconnected", "摄像头重连成功",
                                   {"attempt": attempt})
                return True

            wait_sec = min(base_delay * (2 ** (attempt - 1)), max_delay)
            self._emit_log("warning", "camera.reconnect_retry", "摄像头连接失败，准备重试",
                           {"attempt": attempt, "max_attempts": max_attempts,
                            "retry_in_sec": wait_sec})
            time.sleep(wait_sec)

        self._emit_status("error", "摄像头连接失败，已达到最大重试次数",
                          {"camera_connected": False,
                           "reconnect_attempts": self._reconnect_attempts,
                           "max_attempts": max_attempts})
        return False

    def start(self):
        if self.running:
            return
        self._load_model()
        self.running = True
        self.thread = threading.Thread(target=self._capture_loop, daemon=True)
        self.thread.start()
        self._emit_log("info", "camera.started", f"摄像头 {self.camera_id} 已启动")

    def stop(self):
        self.running = False
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=1)
        self._close_camera()
        self._emit_log("info", "camera.stopped", f"摄像头 {self.camera_id} 已停止")

    # ------------------------------------------------------------------ #
    #  帧捕获（后台线程）
    # ------------------------------------------------------------------ #

    def _capture_loop(self):
        self._last_fps_ts = time.time()
        while self.running:
            if self.cap is None or not self.cap.isOpened():
                if not self._ensure_camera_connected():
                    time.sleep(0.5)
                    continue

            ret, frame = self.cap.read() if self.cap else (False, None)
            if not ret:
                self._emit_log("warning", "camera.read_failed", "摄像头读取失败，尝试重连")
                self._close_camera()
                continue

            now = time.time()
            with self.lock:
                self.frame = frame.copy()
                self.last_frame_ts = now

            # 存入帧缓冲
            with self._buffer_lock:
                self._frame_buffer.append((now, frame.copy()))

            dt = now - self._last_fps_ts
            if dt > 0:
                instant_fps = 1.0 / dt
                self._fps = instant_fps if self._fps == 0 else (self._fps * 0.9 + instant_fps * 0.1)
            self._last_fps_ts = now

    def get_frame(self) -> Optional[np.ndarray]:
        with self.lock:
            return self.frame.copy() if self.frame is not None else None

    # ------------------------------------------------------------------ #
    #  YOLO 检测与告警
    # ------------------------------------------------------------------ #

    def _emit_alert_for_new_tracks(
        self, active_track_ids: list[int], person_count: int, now_ts: float, frame
    ):
        pending = self.tracker.get_pending_tracks(active_track_ids, now_ts)
        if not pending:
            return

        self.tracker.mark_alerted(pending, now_ts)

        screenshot_path = None
        if self.screenshot_mgr.should_save(now_ts, self._alert_total):
            screenshot_path = self.screenshot_mgr.save(frame, now_ts)

        self._alert_total += 1

        if self.db_manager:
            try:
                self.db_manager.create_alert(
                    camera_id=self.camera_id,
                    person_count=person_count,
                    new_track_ids=pending,
                    screenshot_path=screenshot_path,
                    message=f"检测到 {len(pending)} 名新出现人员",
                    level="high",
                )
            except Exception as e:
                self._emit_log("error", "db.insert_failed", f"告警记录写入失败: {e}")

        if self.redis_stats and self.redis_stats.is_enabled():
            try:
                self.redis_stats.incr_today_alerts(self.camera_id)
                self.redis_stats.update_current_persons(self.camera_id, person_count)
            except Exception as e:
                self._emit_log("error", "redis.update_failed", f"Redis 统计更新失败: {e}")

        self._emit(
            AlertMessage(
                timestamp=self._now_iso(),
                level="high",
                message=f"检测到 {len(pending)} 名新出现人员",
                camera_id=self.camera_id,
                data={
                    "person_count": person_count,
                    "new_track_ids": pending,
                    "active_tracks": self.tracker.active_count,
                    "screenshot_path": screenshot_path,
                },
            ).model_dump()
        )

    def _emit_roi_alert(self, roi_alert: dict, frame):
        """发送 ROI 区域告警"""
        now_ts = time.time()
        screenshot_path = None
        if self.screenshot_mgr.should_save(now_ts, self._alert_total):
            screenshot_path = self.screenshot_mgr.save(frame, now_ts)

        self._alert_total += 1

        if self.db_manager:
            try:
                self.db_manager.create_alert(
                    camera_id=self.camera_id,
                    person_count=roi_alert.get("person_count", 1),
                    new_track_ids=roi_alert.get("track_ids", []),
                    screenshot_path=screenshot_path,
                    message=roi_alert.get("message", "ROI 告警"),
                    level=roi_alert.get("alert_level", "high"),
                )
            except Exception as e:
                self._emit_log("error", "db.insert_failed", f"ROI 告警写入失败: {e}")

        self._emit(
            AlertMessage(
                timestamp=self._now_iso(),
                level=roi_alert.get("alert_level", "high"),
                message=roi_alert.get("message", "ROI 告警"),
                camera_id=self.camera_id,
                data={
                    "roi_id": roi_alert.get("roi_id"),
                    "roi_name": roi_alert.get("roi_name"),
                    "roi_type": roi_alert.get("roi_type"),
                    "person_count": roi_alert.get("person_count", 1),
                    "track_ids": roi_alert.get("track_ids", []),
                    "screenshot_path": screenshot_path,
                },
            ).model_dump()
        )

    def _detect(self, frame):
        if self._model is None:
            return frame, 0

        now_ts = time.time()

        # 推理缓存：场景未变化时复用上次结果
        if self._inference_cache_enabled and self._last_results is not None:
            if now_ts - self._last_inference_ts < self._cache_max_age_sec:
                if self._prev_gray is not None:
                    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                    diff = cv2.absdiff(self._prev_gray, gray)
                    if np.mean(diff) < self._scene_change_threshold:
                        # 场景未变化，复用缓存
                        return self._last_results[0].plot(), self._count_from_results(self._last_results)

        results = self._model(frame, verbose=False, conf=self.conf_threshold)
        self._last_results = results
        self._last_inference_ts = now_ts

        # 更新帧差参考
        self._prev_gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        boxes = results[0].boxes
        person_count = int(len(boxes)) if boxes is not None else 0

        bbox_list: list[tuple] = []
        if boxes is not None and person_count > 0:
            for box in boxes:
                x1, y1, x2, y2 = box.xyxy[0].tolist()
                bbox_list.append((float(x1), float(y1), float(x2), float(y2)))

        active_track_ids = self.tracker.associate(bbox_list, now_ts)
        self._emit_alert_for_new_tracks(active_track_ids, person_count, now_ts, frame)

        # ROI 区域检测
        if bbox_list and active_track_ids:
            roi_alerts = self.roi_detector.check_all(self.camera_id, bbox_list, active_track_ids)
            for alert in roi_alerts:
                self._emit_roi_alert(alert, frame)

        return results[0].plot(), person_count

    @staticmethod
    def _count_from_results(results) -> int:
        boxes = results[0].boxes
        return int(len(boxes)) if boxes is not None else 0

    def _get_adaptive_detect_interval(self) -> int:
        """根据场景变化率自适应调整检测间隔"""
        if not self._adaptive_skip or self._prev_gray is None:
            return self.detect_every_n

        frame = self.get_frame()
        if frame is None:
            return self.detect_every_n

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        diff = cv2.absdiff(self._prev_gray, gray)
        mean_diff = np.mean(diff)

        if mean_diff > self._scene_change_threshold * 3:
            return 1  # 场景剧烈变化，每帧检测
        elif mean_diff > self._scene_change_threshold:
            return max(1, self._base_detect_every_n // 2)
        else:
            return self._base_detect_every_n * 2  # 静态场景，跳更多帧

    def get_frame_buffer(self, seconds: float = 10.0) -> list[tuple]:
        """获取最近 N 秒的帧缓冲（用于录像回放）"""
        cutoff = time.time() - seconds
        with self._buffer_lock:
            return [(ts, f.copy()) for ts, f in self._frame_buffer if ts >= cutoff]

    # ------------------------------------------------------------------ #
    #  MJPEG 流生成器
    # ------------------------------------------------------------------ #

    def get_frame_generator(self) -> Generator[bytes, None, None]:
        last_encode_ts = time.time()

        while self.running:
            frame = self.get_frame()
            if frame is None:
                time.sleep(0.01)
                continue

            self._frame_count += 1

            try:
                if self.detection_enabled and self._model is not None:
                    if self._frame_count % self.detect_every_n == 0:
                        output_frame, _ = self._detect(frame)
                    elif self._last_results is not None:
                        output_frame = self._last_results[0].plot()
                    else:
                        output_frame = frame
                else:
                    output_frame = frame
            except Exception as e:
                self._emit_log("warning", "detection.error", f"检测异常，跳过本帧: {e}")
                output_frame = frame

            ret, jpeg = cv2.imencode(".jpg", output_frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
            if ret:
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n\r\n"
                    + jpeg.tobytes()
                    + b"\r\n"
                )

            now = time.time()
            elapsed = now - last_encode_ts
            last_encode_ts = now
            time.sleep(max(0.001, 0.033 - elapsed))

    # ------------------------------------------------------------------ #
    #  运行时配置（供 API 调用）
    # ------------------------------------------------------------------ #

    def set_conf(self, conf: float):
        self.conf_threshold = max(0.1, min(0.95, conf))

    def toggle_detection(self, enabled: bool):
        self.detection_enabled = enabled

    def get_status(self) -> dict:
        now = time.time()
        last_frame_age_ms = (
            int((now - self.last_frame_ts) * 1000) if self.last_frame_ts > 0 else None
        )
        return {
            "camera_id": self.camera_id,
            "running": self.running,
            "connected": self.connected,
            "detection_enabled": self.detection_enabled,
            "conf_threshold": self.conf_threshold,
            "model_loaded": self._model is not None,
            "fps": round(self._fps, 2),
            "last_frame_age_ms": last_frame_age_ms,
            "reconnect_attempts": self._reconnect_attempts,
            "active_tracks": self.tracker.active_count,
            "alert_total": self._alert_total,
            "resolution": f"{self.width}x{self.height}" if self.width and self.height else None,
        }
