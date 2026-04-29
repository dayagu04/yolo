"""
通知器基类
"""
import logging
from abc import ABC, abstractmethod
from typing import Optional


class BaseNotifier(ABC):
    """所有通知器的基类"""

    def __init__(self, config: dict):
        self.config = config
        self.enabled = config.get("enabled", False)
        self.logger = logging.getLogger(self.__class__.__name__)

    @abstractmethod
    async def send_alert(self, alert: dict, screenshot_path: Optional[str] = None) -> bool:
        """发送告警通知，返回是否成功"""
        ...

    def _should_push_level(self, alert_level: str, push_level: str) -> bool:
        """判断告警级别是否需要推送"""
        level_priority = {"low": 1, "medium": 2, "high": 3}
        return level_priority.get(alert_level, 3) >= level_priority.get(push_level, 3)
