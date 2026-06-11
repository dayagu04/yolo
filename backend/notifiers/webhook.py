"""
通用 Webhook 推送
"""
import ipaddress
import json
from typing import Optional
from urllib.parse import urlparse

import aiohttp

from backend.notifiers.base import BaseNotifier


def _is_safe_webhook_url(url: str, allow_private: bool = False) -> tuple[bool, str]:
    """校验 webhook URL，防止 SSRF。

    返回 (是否安全, 原因)。allow_private=True 时放行内网（用于内部告警系统）。
    """
    if not url:
        return False, "空 URL"
    try:
        parsed = urlparse(url)
    except Exception as e:
        return False, f"URL 解析失败: {e}"
    if parsed.scheme not in ("http", "https"):
        return False, f"仅允许 http/https，当前: {parsed.scheme}"
    host = parsed.hostname
    if not host:
        return False, "缺少 hostname"
    if allow_private:
        return True, ""
    # 字面 IP：拒绝任何私有/回环/链路本地/保留段
    try:
        ip = ipaddress.ip_address(host)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            return False, f"拒绝内网/保留地址: {host}"
    except ValueError:
        # 域名场景：显式拒绝常见内网/元数据主机名
        lowered = host.lower()
        blocked_hosts = {"localhost", "metadata", "metadata.google.internal"}
        if lowered in blocked_hosts:
            return False, f"拒绝内网主机名: {host}"
    return True, ""


class WebhookNotifier(BaseNotifier):
    """通用 Webhook：POST JSON 到用户配置的 URL"""

    def __init__(self, config: dict):
        super().__init__(config)
        url = config.get("webhook_url", "")
        # allow_private_url=True 用于受控内网环境（如内部 IM bot）
        self._allow_private = bool(config.get("allow_private_url", False))
        self.webhook_url = url
        self.push_level = config.get("push_level", "high")
        raw_headers = config.get("headers", {})
        self.headers = raw_headers if isinstance(raw_headers, dict) else {}

        if self.enabled and url:
            ok, reason = _is_safe_webhook_url(url, allow_private=self._allow_private)
            if not ok:
                self.logger.error(f"Webhook URL 校验失败，已禁用通道: {reason}")
                self.enabled = False

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

        # 用户自定义 headers 在前，Content-Type 强制后置覆盖
        headers = {**self.headers, "Content-Type": "application/json"}

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
