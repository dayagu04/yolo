"""
告警管理模块

负责告警生成、去重、截图触发，感知推理异常（M5 修复）。
"""
import time
from typing import Optional, Callable
import numpy as np
from backend.tracker import PersonTracker
from backend.screenshot import ScreenshotManager


class AlertManager:
    """告警管理器（跟踪、去重、截图、异常感知）"""

    def __init__(
        self,
        camera_id: int,
        tracker: PersonTracker,
        screenshot_manager: Optional[ScreenshotManager],
        signal_callback: Optional[Callable],
        cooldown_sec: float = 5.0,
    ):
        """
        Args:
            camera_id: 摄像头 ID
            tracker: 人员跟踪器
            screenshot_manager: 截图管理器
            signal_callback: 告警回调（发送到 WebSocket/通知）
            cooldown_sec: 告警冷却时间
        """
        self.camera_id = camera_id
        self.tracker = tracker
        self.screenshot_manager = screenshot_manager
        self.signal_callback = signal_callback
        self.cooldown_sec = cooldown_sec

        self.alert_count = 0
        self._last_alert_ts = 0.0
        self._inference_error_paused = False  # M5: 推理异常时暂停告警

    def process_detections(
        self,
        frame: np.ndarray,
        results,
        person_count: int,
        inference_error: Optional[str],
        frame_ts: float,
    ) -> int:
        """
        处理检测结果，生成告警

        Args:
            frame: 当前帧
            results: YOLO 检测结果
            person_count: 人数
            inference_error: 推理异常消息（M5 新增）
            frame_ts: 帧时间戳

        Returns:
            告警数量
        """
        # M5 修复：推理异常时暂停告警，恢复后继续
        if inference_error:
            if not self._inference_error_paused:
                self._inference_error_paused = True
                self._emit_log("warning", "inference.error",
                              f"推理异常，暂停告警: {inference_error}")
            return 0

        if self._inference_error_paused:
            self._inference_error_paused = False
            self._emit_log("info", "inference.recovered", "推理恢复，告警恢复")

        # 无检测结果，跳过
        if results is None or person_count == 0:
            return 0

        # 提取 bbox
        boxes = results[0].boxes
        if boxes is None:
            return 0

        bbox_list = []
        for box in boxes:
            cls_id = int(box.cls[0])
            if cls_id == 0:  # person
                x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                bbox_list.append((float(x1), float(y1), float(x2), float(y2)))

        # 更新跟踪
        self.tracker.update(bbox_list)

        # 获取新出现的追踪目标
        new_tracks = self.tracker.get_pending_tracks(self.cooldown_sec)

        if not new_tracks:
            return 0

        # 生成告警
        return self._emit_alerts_for_new_tracks(new_tracks, frame, person_count, frame_ts)

    def _emit_alerts_for_new_tracks(
        self, new_tracks: list, frame: np.ndarray, person_count: int, frame_ts: float
    ) -> int:
        """为新追踪目标生成告警"""
        now = time.time()

        # 全局冷却检查
        if now - self._last_alert_ts < self.cooldown_sec:
            return 0

        alert_level = self._calculate_alert_level(person_count)
        screenshot_path = None

        # 截图
        if self.screenshot_manager:
            screenshot_path = self.screenshot_manager.save_if_needed(
                frame, alert_level, len(new_tracks)
            )

        # 发送告警信号
        if self.signal_callback:
            track_ids = [t["track_id"] for t in new_tracks]
            message = {
                "type": "alert",
                "level": alert_level,
                "camera_id": self.camera_id,
                "message": f"检测到 {len(new_tracks)} 个新目标",
                "data": {
                    "person_count": person_count,
                    "new_tracks": track_ids,
                    "screenshot_path": screenshot_path,
                    "timestamp": frame_ts,
                },
            }
            self.signal_callback(message)

        self.alert_count += len(new_tracks)
        self._last_alert_ts = now

        return len(new_tracks)

    def _calculate_alert_level(self, person_count: int) -> str:
        """根据人数计算告警级别"""
        if person_count >= 10:
            return "high"
        elif person_count >= 5:
            return "medium"
        return "low"

    def _emit_log(self, level: str, event: str, message: str):
        """发送日志信号"""
        if self.signal_callback:
            self.signal_callback({
                "type": "log",
                "level": level,
                "event": event,
                "camera_id": self.camera_id,
                "message": message,
                "data": {},
            })

    def get_alert_count(self) -> int:
        return self.alert_count

    def get_active_track_count(self) -> int:
        return self.tracker.active_count()
