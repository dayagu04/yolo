"""
后端结构化日志系统（JSON + 内存环形缓冲 + 文件持久化）
"""
import json
import logging
import logging.handlers
import sys
import threading
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


# 敏感字段：写日志前一律脱敏。匹配规则按 key 名小写包含。
_SENSITIVE_KEY_HINTS = ("password", "secret", "token", "api_key", "apikey", "authorization")


def _sanitize(value: Any) -> Any:
    """递归脱敏：dict 中名字命中敏感关键词的字段值替换为 ***"""
    if isinstance(value, dict):
        return {
            k: ("***" if any(h in str(k).lower() for h in _SENSITIVE_KEY_HINTS) else _sanitize(v))
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [_sanitize(v) for v in value]
    return value


class StructuredLogger:
    def __init__(
        self,
        name: str = "surveillance",
        max_entries: int = 500,
        log_dir: str = "logs",
        log_to_file: bool = True,
    ):
        self._buffer = deque(maxlen=max_entries)
        # 保护 _buffer 的并发读写：写入来自摄像头线程，读取来自事件循环线程
        self._buffer_lock = threading.Lock()
        self.logger = logging.getLogger(name)
        self.logger.setLevel(logging.INFO)

        if not self.logger.handlers:
            # 强制使用 UTF-8 输出，避免 Windows 控制台 GBK 编码导致中文乱码
            stream = open(sys.stdout.fileno(), mode="w", encoding="utf-8", buffering=1, closefd=False)
            handler = logging.StreamHandler(stream)
            handler.setFormatter(logging.Formatter("%(message)s"))
            self.logger.addHandler(handler)

            # 文件持久化：按日期轮转，保留 30 天
            if log_to_file:
                log_path = Path(log_dir)
                log_path.mkdir(parents=True, exist_ok=True)
                file_handler = logging.handlers.TimedRotatingFileHandler(
                    filename=str(log_path / "surveillance.jsonl"),
                    when="midnight",
                    interval=1,
                    backupCount=30,
                    encoding="utf-8",
                    utc=False,
                )
                file_handler.setFormatter(logging.Formatter("%(message)s"))
                self.logger.addHandler(file_handler)

    def _iso_now(self) -> str:
        return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")

    def log(self, level: str, event: str, message: str, camera_id: Optional[int] = None, data: Optional[dict] = None):
        payload = {
            "timestamp": self._iso_now(),
            "level": level,
            "event": event,
            "camera_id": camera_id,
            "message": message,
            "data": _sanitize(data) if data else {},
        }
        # 锁内 append + 序列化前的快照，避免与 get_recent_logs 的 list(...) 撕裂读
        with self._buffer_lock:
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
        with self._buffer_lock:
            return list(self._buffer)[-limit:]


structured_logger = StructuredLogger()
