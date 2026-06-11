"""
邮件通知器
"""
import asyncio
import html
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional
from backend.notifiers.base import BaseNotifier


def _sanitize_header(value: str) -> str:
    """清理邮件头字段，移除 CR/LF 防止头注入。"""
    return str(value).replace("\r", " ").replace("\n", " ").strip()


class EmailNotifier(BaseNotifier):
    """SMTP 邮件告警通知"""

    def __init__(self, config: dict):
        super().__init__(config)
        self.smtp_host = config.get("smtp_host", "")
        self.smtp_port = config.get("smtp_port", 465)
        self.smtp_user = config.get("smtp_user", "")
        self.smtp_password = config.get("smtp_password", "")
        self.use_ssl = config.get("use_ssl", True)
        self.from_addr = config.get("from_addr", self.smtp_user)
        self.to_addrs: list[str] = config.get("to_addrs", [])
        self.push_level = config.get("push_level", "high")

    async def send_alert(self, alert: dict, screenshot_path: Optional[str] = None) -> bool:
        if not self.enabled or not self.smtp_host or not self.to_addrs:
            return False

        alert_level = alert.get("level", "high")
        if not self._should_push_level(alert_level, self.push_level):
            return False

        data = alert.get("data", {})
        message = alert.get("message", "检测到人员")
        camera_id = alert.get("camera_id", 0)
        timestamp = alert.get("timestamp", "")
        person_count = data.get("person_count", 0)

        # Subject 走单行字段，必须移除 CR/LF（防邮件头注入）
        subject = _sanitize_header(f"[安防告警] 摄像头 {camera_id} - {message}")

        # HTML body 中所有用户可控内容都要 escape
        camera_id_h = html.escape(str(camera_id))
        timestamp_h = html.escape(str(timestamp))
        person_count_h = html.escape(str(person_count))
        message_h = html.escape(str(message))

        body = (
            f"<h3>⚠️ 安防告警</h3>"
            f"<table style='border-collapse:collapse;'>"
            f"<tr><td style='padding:4px 12px;border:1px solid #ddd;font-weight:bold'>摄像头</td><td style='padding:4px 12px;border:1px solid #ddd'>{camera_id_h}</td></tr>"
            f"<tr><td style='padding:4px 12px;border:1px solid #ddd;font-weight:bold'>时间</td><td style='padding:4px 12px;border:1px solid #ddd'>{timestamp_h}</td></tr>"
            f"<tr><td style='padding:4px 12px;border:1px solid #ddd;font-weight:bold'>人数</td><td style='padding:4px 12px;border:1px solid #ddd'>{person_count_h} 人</td></tr>"
            f"<tr><td style='padding:4px 12px;border:1px solid #ddd;font-weight:bold'>消息</td><td style='padding:4px 12px;border:1px solid #ddd'>{message_h}</td></tr>"
            f"</table>"
        )

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._send_sync, subject, body)

    def _send_sync(self, subject: str, body: str) -> bool:
        server = None
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = _sanitize_header(self.from_addr)
            # 收件人逐个清理，再以逗号拼接
            msg["To"] = ", ".join(_sanitize_header(a) for a in self.to_addrs)
            msg.attach(MIMEText(body, "html", "utf-8"))

            if self.use_ssl:
                server = smtplib.SMTP_SSL(self.smtp_host, self.smtp_port, timeout=10)
            else:
                server = smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=10)
                server.starttls()

            server.login(self.smtp_user, self.smtp_password)
            server.sendmail(self.from_addr, self.to_addrs, msg.as_string())
            self.logger.info(f"邮件推送成功: {self.to_addrs}")
            return True
        except Exception as e:
            self.logger.error(f"邮件推送异常: {e}")
            return False
        finally:
            # 异常路径也要释放 SMTP 连接
            if server is not None:
                try:
                    server.quit()
                except Exception:
                    pass
