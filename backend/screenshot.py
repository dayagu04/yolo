"""
截图管理器 - 告警截图保存策略与文件写入
"""
import cv2
from datetime import datetime
from pathlib import Path
from typing import Optional, Callable


class ScreenshotManager:
    """告警截图保存管理器，支持 first_only / all / interval 三种模式"""

    def __init__(
        self,
        camera_id: int,
        config: dict,
        root_path: Path,
        emit_log: Optional[Callable] = None,
    ):
        self.camera_id = camera_id
        self.config = config
        self.root_path = root_path
        self._emit_log = emit_log or (lambda *a, **kw: None)
        self._last_ts: float = 0.0

    def should_save(self, now_ts: float, alert_total: int) -> bool:
        if not self.config.get("enabled", True):
            return False
        mode = self.config.get("save_mode", "first_only")
        if mode == "all":
            return True
        if mode == "first_only":
            return alert_total == 0
        if mode == "interval":
            return now_ts - self._last_ts >= self.config.get("interval_sec", 10)
        return False

    def save(self, frame, now_ts: float) -> Optional[str]:
        """保存截图，返回相对路径；失败返回 None"""
        try:
            save_dir = self.config.get("save_dir", "data/screenshots")
            date_str = datetime.now().strftime("%Y-%m-%d")
            day_dir = self.root_path / save_dir / date_str
            day_dir.mkdir(parents=True, exist_ok=True)

            ts = datetime.now().strftime("%H%M%S_%f")[:-3]
            filename = f"cam{self.camera_id}_{ts}.jpg"
            quality = self.config.get("quality", 75)
            cv2.imwrite(
                str(day_dir / filename), frame,
                [cv2.IMWRITE_JPEG_QUALITY, quality],
            )
            self._last_ts = now_ts
            return f"{date_str}/{filename}"
        except Exception as e:
            self._emit_log("error", "screenshot.save_failed", f"截图保存失败: {e}")
            return None
