"""
钉钉 Webhook 推送
"""
import aiohttp
from typing import Optional
from backend.notifiers.base import BaseNotifier


class DingTalkNotifier(BaseNotifier):
    """钉钉自定义机器人 Webhook 推送"""

    def __init__(self, config: dict):
        super().__init__(config)
        self.webhook_url = config.get("webhook_url", "")
        self.push_level = config.get("push_level", "high")

    async def send_alert(self, alert: dict, screenshot_path: Optional[str] = None) -> bool:
        if not self.enabled or not self.webhook_url:
            return False

        alert_level = alert.get("level", "high")
        if not self._should_push_level(alert_level, self.push_level):
            return False

        data = alert.get("data", {})
        message = alert.get("message", "检测到人员")
        camera_id = alert.get("camera_id", 0)
        timestamp = alert.get("timestamp", "")
        person_count = data.get("person_count", 0)

        text = (
            f"### ⚠️ 安防告警\n"
            f"- 摄像头: {camera_id}\n"
            f"- 时间: {timestamp}\n"
            f"- 人数: {person_count} 人\n"
            f"- 消息: {message}"
        )

        payload = {
            "msgtype": "markdown",
            "markdown": {"title": "安防告警", "text": text},
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(self.webhook_url, json=payload, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if data.get("errcode") == 0:
                            self.logger.info("钉钉推送成功")
                            return True
                        self.logger.error(f"钉钉推送失败: {data}")
                        return False
                    self.logger.error(f"钉钉推送失败: {resp.status}")
                    return False
        except Exception as e:
            self.logger.error(f"钉钉推送异常: {e}")
            return False
