"""
通用 Webhook 推送
"""
import aiohttp
import json
from typing import Optional
from backend.notifiers.base import BaseNotifier


class WebhookNotifier(BaseNotifier):
    """通用 Webhook：POST JSON 到用户配置的 URL"""

    def __init__(self, config: dict):
        super().__init__(config)
        self.webhook_url = config.get("webhook_url", "")
        self.push_level = config.get("push_level", "high")
        self.headers = config.get("headers", {})

    async def send_alert(self, alert: dict, screenshot_path: Optional[str] = None) -> bool:
        if not self.enabled or not self.webhook_url:
            return False

        alert_level = alert.get("level", "high")
        if not self._should_push_level(alert_level, self.push_level):
            return False

        payload = {
            "event": "alert",
            "camera_id": alert.get("camera_id"),
            "timestamp": alert.get("timestamp"),
            "level": alert_level,
            "message": alert.get("message"),
            "data": alert.get("data", {}),
        }

        headers = {"Content-Type": "application/json", **self.headers}

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.webhook_url, data=json.dumps(payload),
                    headers=headers, timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    if 200 <= resp.status < 300:
                        self.logger.info(f"Webhook 推送成功: {resp.status}")
                        return True
                    self.logger.error(f"Webhook 推送失败: {resp.status}")
                    return False
        except Exception as e:
            self.logger.error(f"Webhook 推送异常: {e}")
            return False
