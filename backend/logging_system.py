"""
后端结构化日志系统（JSON + 内存环形缓冲）
"""
from collections import deque
from datetime import datetime, timezone
from typing import Optional
import json
import logging
import sys


class StructuredLogger:
    def __init__(self, name: str = "surveillance", max_entries: int = 500):
        self._buffer = deque(maxlen=max_entries)
        self.logger = logging.getLogger(name)
        self.logger.setLevel(logging.INFO)

        if not self.logger.handlers:
            # 强制使用 UTF-8 输出，避免 Windows 控制台 GBK 编码导致中文乱码
            stream = open(sys.stdout.fileno(), mode="w", encoding="utf-8", buffering=1, closefd=False)
            handler = logging.StreamHandler(stream)
            handler.setFormatter(logging.Formatter("%(message)s"))
            self.logger.addHandler(handler)

    def _iso_now(self) -> str:
        return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")

    def log(self, level: str, event: str, message: str, camera_id: Optional[int] = None, data: Optional[dict] = None):
        payload = {
            "timestamp": self._iso_now(),
            "level": level,
            "event": event,
            "camera_id": camera_id,
            "message": message,
            "data": data or {},
        }
        self._buffer.append(payload)
        line = json.dumps(payload, ensure_ascii=False)

        if level == "error":
            self.logger.error(line)
        elif level == "warning":
            self.logger.warning(line)
        else:
            self.logger.info(line)

        return payload

    def get_recent_logs(self, limit: int = 100) -> list[dict]:
        limit = max(1, min(500, limit))
        return list(self._buffer)[-limit:]


structured_logger = StructuredLogger()
