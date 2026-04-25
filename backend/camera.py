import cv2
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, Generator, Callable

import numpy as np

# 确保项目根目录在 sys.path 中
ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.schemas import AlertMessage, StatusMessage, LogMessage

MODEL_PATH = Path(__file__).parent.parent / "models" / "person_best.pt"


class CameraManager:
    def __init__(
        self,
        camera_id: int = 0,
        width: Optional[int] = None,
        height: Optional[int] = None,
        signal_callback: Optional[Callable[[dict], None]] = None,
        db_manager=None,
        redis_stats=None,
        screenshot_config: Optional[dict] = None,
    ):
        self.camera_id = camera_id
        self.width = width
        self.height = height
        self.signal_callback = signal_callback
        self.db_manager = db_manager
        self.redis_stats = redis_stats
        self.screenshot_config = screenshot_config or {}
        self._last_screenshot_ts: float = 0.0

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

        # YOLO 检测状态
        self.detection_enabled = True
        self.conf_threshold = 0.5
        self.detect_every_n = 2  # 每 N 帧检测一次（性能优化）
        self._frame_count = 0
        self._last_results = None
        self._last_alert_time = 0.0
        self._alert_total = 0

        # 人员 Track 管理（轻量去重）
        self._next_track_id = 1
        self._tracks: dict[int, dict] = {}
        self._track_ttl_sec = 2.0
        self._alert_cooldown_sec = 5.0

        # 延迟加载模型（避免导入时崩溃）
        self._model = None

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
            self._emit_log("info", "model.loaded", f"YOLO 模型已加载: {MODEL_PATH}")
        except Exception as e:
            self._model = None
            self._emit_log("error", "model.load_failed", f"YOLO 模型加载失败: {e}")

    # ------------------------------------------------------------------ #
    #  摄像头生命周期
    # ------------------------------------------------------------------ #

    def _open_camera(self) -> bool:
        # Windows 下优先使用 DirectShow 后端，避免 MSMF 读帧失败问题
        cap = cv2.VideoCapture(self.camera_id, cv2.CAP_DSHOW)

        if not cap.isOpened():
            cap.release()
            return False

        # 仅在明确指定分辨率时才设置（未指定则保持摄像头原生分辨率）
        # 注意：强制设置摄像头不支持的分辨率可能导致 DSHOW 返回黑帧
        if self.width is not None:
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        if self.height is not None:
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)

        # 读取实际分辨率（摄像头可能不支持设置的值）
        actual_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        actual_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

        # DSHOW 首帧通常为黑帧（曝光预热），丢弃前 5 帧
        for _ in range(5):
            cap.read()

        # 以实际分辨率为准（覆盖初始设置）
        self.width = actual_width
        self.height = actual_height

        self.cap = cap
        self.connected = True
        self._reconnect_attempts = 0
        self._emit_status(
            "info",
            f"摄像头已连接 ({actual_width}x{actual_height})",
            {"camera_connected": True, "model_loaded": self._model is not None,
             "resolution": f"{actual_width}x{actual_height}"},
        )
        return True

    def _close_camera(self):
        if self.cap:
            self.cap.release()
        self.cap = None
        self.connected = False

    def _ensure_camera_connected(self) -> bool:
        for attempt in (1, 2, 3):
            if not self.running:
                return False
            self._reconnect_attempts = attempt
            if self._open_camera():
                if attempt > 1:
                    self._emit_log(
                        "info",
                        "camera.reconnected",
                        "摄像头重连成功",
                        {"attempt": attempt},
                    )
                return True

            wait_sec = 2**attempt  # 2 / 4 / 8
            self._emit_log(
                "warning",
                "camera.reconnect_retry",
                "摄像头连接失败，准备重试",
                {"attempt": attempt, "retry_in_sec": wait_sec},
            )
            time.sleep(wait_sec)

        self._emit_status(
            "error",
            "摄像头连接失败",
            {"camera_connected": False, "reconnect_attempts": self._reconnect_attempts},
        )
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

            dt = now - self._last_fps_ts
            if dt > 0:
                instant_fps = 1.0 / dt
                self._fps = instant_fps if self._fps == 0 else (self._fps * 0.9 + instant_fps * 0.1)
            self._last_fps_ts = now

            # 不在捕获线程中 sleep，让摄像头以最大速度读取
            # 这样可以避免缓冲区积压导致延迟

    def get_frame(self) -> Optional[np.ndarray]:
        with self.lock:
            return self.frame.copy() if self.frame is not None else None

    # ------------------------------------------------------------------ #
    #  YOLO 检测与告警
    # ------------------------------------------------------------------ #

    @staticmethod
    def _iou(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> float:
        ax1, ay1, ax2, ay2 = a
        bx1, by1, bx2, by2 = b
        inter_x1 = max(ax1, bx1)
        inter_y1 = max(ay1, by1)
        inter_x2 = min(ax2, bx2)
        inter_y2 = min(ay2, by2)
        iw = max(0.0, inter_x2 - inter_x1)
        ih = max(0.0, inter_y2 - inter_y1)
        inter = iw * ih
        if inter <= 0:
            return 0.0
        area_a = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
        area_b = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
        union = area_a + area_b - inter
        return inter / union if union > 0 else 0.0

    def _associate_tracks(self, boxes: list[tuple[float, float, float, float]], now_ts: float) -> list[int]:
        matched_track_ids = set()
        active_track_ids: list[int] = []

        for box in boxes:
            best_track_id = None
            best_iou = 0.0

            # 中心点距离辅助判断
            bx_c = (box[0] + box[2]) / 2
            by_c = (box[1] + box[3]) / 2

            for track_id, track in self._tracks.items():
                if track_id in matched_track_ids:
                    continue
                iou = self._iou(box, track["bbox"])

                # 中心点距离（像素）
                tc = track["center"]
                dist = ((bx_c - tc[0]) ** 2 + (by_c - tc[1]) ** 2) ** 0.5

                # IoU > 0.3 或中心点距离 < 50px 时认为是同一人
                if (iou > 0.3 or dist < 50.0) and iou > best_iou:
                    best_iou = iou
                    best_track_id = track_id

            if best_track_id is None:
                # 新 Track
                track_id = self._next_track_id
                self._next_track_id += 1
                self._tracks[track_id] = {
                    "bbox": box,
                    "center": (bx_c, by_c),
                    "last_seen": now_ts,
                    "alerted": False,
                }
                active_track_ids.append(track_id)
                matched_track_ids.add(track_id)   # 修复：新 Track 也要占位，防止后续 box 重复匹配
            else:
                self._tracks[best_track_id]["bbox"] = box
                self._tracks[best_track_id]["center"] = (bx_c, by_c)
                self._tracks[best_track_id]["last_seen"] = now_ts
                active_track_ids.append(best_track_id)
                matched_track_ids.add(best_track_id)

        # 清理超时 Track（消失即可再次告警）
        expired = [
            track_id
            for track_id, track in self._tracks.items()
            if now_ts - track["last_seen"] > self._track_ttl_sec
        ]
        for track_id in expired:
            self._tracks.pop(track_id, None)

        return active_track_ids

    def _save_screenshot(self, frame: np.ndarray) -> Optional[str]:
        """保存截图，返回相对路径（配置的 save_dir 下按日期分目录）"""
        try:
            save_dir = self.screenshot_config.get("save_dir", "data/screenshots")
            screenshots_dir = ROOT / save_dir
            date_str = datetime.now().strftime("%Y-%m-%d")
            day_dir = screenshots_dir / date_str
            day_dir.mkdir(parents=True, exist_ok=True)

            timestamp = datetime.now().strftime("%H%M%S_%f")[:-3]
            filename = f"cam{self.camera_id}_{timestamp}.jpg"
            filepath = day_dir / filename

            quality = self.screenshot_config.get("quality", 75)
            cv2.imwrite(str(filepath), frame, [cv2.IMWRITE_JPEG_QUALITY, quality])

            return f"{date_str}/{filename}"
        except Exception as e:
            self._emit_log("error", "screenshot.save_failed", f"截图保存失败: {e}")
            return None

    def _should_save_screenshot(self, now_ts: float) -> bool:
        """根据 save_mode 判断是否需要保存截图"""
        if not self.screenshot_config.get("enabled", True):
            return False
        mode = self.screenshot_config.get("save_mode", "first_only")
        if mode == "all":
            return True
        if mode == "first_only":
            return self._alert_total == 0
        if mode == "interval":
            interval = self.screenshot_config.get("interval_sec", 10)
            return now_ts - self._last_screenshot_ts >= interval
        return False

    def _emit_alert_for_new_tracks(self, active_track_ids: list[int], person_count: int, now_ts: float, frame: np.ndarray):
        pending = [tid for tid in active_track_ids if not self._tracks.get(tid, {}).get("alerted")]
        if not pending:
            return

        # 全局频控兜底：防止抖动误报
        if now_ts - self._last_alert_time < self._alert_cooldown_sec:
            return

        self._last_alert_time = now_ts
        for tid in pending:
            if tid in self._tracks:
                self._tracks[tid]["alerted"] = True

        # 保存截图
        screenshot_path = None
        if self._should_save_screenshot(now_ts):
            screenshot_path = self._save_screenshot(frame)
            if screenshot_path:
                self._last_screenshot_ts = now_ts

        self._alert_total += 1

        # 写入数据库
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

        # 更新 Redis 统计
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
                    "active_tracks": len(self._tracks),
                    "screenshot_path": screenshot_path,
                },
            ).model_dump()
        )

    def _detect(self, frame: np.ndarray):
        if self._model is None:
            return frame, 0

        results = self._model(frame, verbose=False, conf=self.conf_threshold)
        self._last_results = results

        boxes = results[0].boxes
        person_count = int(len(boxes)) if boxes is not None else 0

        now_ts = time.time()
        bbox_list: list[tuple[float, float, float, float]] = []
        if boxes is not None and person_count > 0:
            for box in boxes:
                x1, y1, x2, y2 = box.xyxy[0].tolist()
                bbox_list.append((float(x1), float(y1), float(x2), float(y2)))

        active_track_ids = self._associate_tracks(bbox_list, now_ts)
        self._emit_alert_for_new_tracks(active_track_ids, person_count, now_ts, frame)

        annotated = results[0].plot()
        return annotated, person_count

    # ------------------------------------------------------------------ #
    #  MJPEG 流生成器
    # ------------------------------------------------------------------ #

    def get_frame_generator(self) -> Generator[bytes, None, None]:
        last_encode_ts = time.time()

        while self.running:
            frame = self.get_frame()
            if frame is None:
                time.sleep(0.01)  # 减少空闲等待时间
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

            # 动态调整帧率：根据实际处理时间调整 sleep
            now = time.time()
            elapsed = now - last_encode_ts
            last_encode_ts = now

            # 目标 30 fps (33ms/frame)，减去已用时间
            target_interval = 0.033
            sleep_time = max(0.001, target_interval - elapsed)
            time.sleep(sleep_time)

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
            "active_tracks": len(self._tracks),
            "alert_total": self._alert_total,
            "resolution": f"{self.width}x{self.height}" if self.width and self.height else None,
        }
