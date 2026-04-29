"""
通知器模块
支持多种推送渠道：飞书、企业微信、钉钉、邮件、通用 Webhook
"""
from backend.notifiers.base import BaseNotifier
from backend.notifiers.wechat_work import WeChatWorkNotifier
from backend.notifiers.dingtalk import DingTalkNotifier
from backend.notifiers.email_notifier import EmailNotifier
from backend.notifiers.webhook import WebhookNotifier

__all__ = [
    "BaseNotifier", "WeChatWorkNotifier", "DingTalkNotifier",
    "EmailNotifier", "WebhookNotifier",
]
