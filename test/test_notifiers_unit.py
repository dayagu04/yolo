"""notifiers/ 单元测试"""
import pytest
from unittest.mock import patch, AsyncMock, MagicMock


# ── 基类测试 ──

class TestBaseNotifier:
    def test_should_push_level(self):
        from backend.notifiers.base import BaseNotifier

        class DummyNotifier(BaseNotifier):
            async def send_alert(self, message, screenshot_path=None):
                pass

        n = DummyNotifier({"enabled": True, "push_levels": ["high", "medium"]})
        # _should_push_level(alert_level, push_level) — alert>=push 则推送
        assert n._should_push_level("high", "high") is True
        assert n._should_push_level("high", "low") is True
        assert n._should_push_level("low", "high") is False

    def test_default_push_levels(self):
        from backend.notifiers.base import BaseNotifier

        class DummyNotifier(BaseNotifier):
            async def send_alert(self, message, screenshot_path=None):
                pass

        n = DummyNotifier({"enabled": True})
        # 默认 push_level="low"，所有级别都 >= low
        assert n._should_push_level("high", "low") is True
        assert n._should_push_level("medium", "low") is True
        assert n._should_push_level("low", "low") is True


# ── 企业微信测试 ──

class TestWeChatWorkNotifier:
    def test_init(self):
        from backend.notifiers.wechat_work import WeChatWorkNotifier
        n = WeChatWorkNotifier({"enabled": True, "webhook_url": "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=test"})
        assert n.enabled is True

    def test_disabled(self):
        from backend.notifiers.wechat_work import WeChatWorkNotifier
        n = WeChatWorkNotifier({"enabled": False})
        assert n.enabled is False

    @pytest.mark.asyncio
    async def test_send_disabled(self):
        from backend.notifiers.wechat_work import WeChatWorkNotifier
        n = WeChatWorkNotifier({"enabled": False})
        result = await n.send_alert({"level": "high", "message": "test"})
        assert result is False

    @pytest.mark.asyncio
    async def test_send_filtered(self):
        from backend.notifiers.wechat_work import WeChatWorkNotifier
        n = WeChatWorkNotifier({"enabled": True, "webhook_url": "https://test.com", "push_level": "high"})
        result = await n.send_alert({"level": "low", "message": "test"})
        assert result is False


# ── 钉钉测试 ──

class TestDingTalkNotifier:
    def test_init(self):
        from backend.notifiers.dingtalk import DingTalkNotifier
        n = DingTalkNotifier({"enabled": True, "webhook_url": "https://oapi.dingtalk.com/robot/send?access_token=test"})
        assert n.enabled is True

    @pytest.mark.asyncio
    async def test_send_disabled(self):
        from backend.notifiers.dingtalk import DingTalkNotifier
        n = DingTalkNotifier({"enabled": False})
        result = await n.send_alert({"level": "high", "message": "test"})
        assert result is False


# ── 邮件测试 ──

class TestEmailNotifier:
    def test_init(self):
        from backend.notifiers.email_notifier import EmailNotifier
        n = EmailNotifier({
            "enabled": True, "smtp_host": "smtp.test.com", "smtp_port": 465,
            "username": "test@test.com", "password": "pass", "to_addrs": ["a@b.com"],
        })
        assert n.enabled is True

    @pytest.mark.asyncio
    async def test_send_disabled(self):
        from backend.notifiers.email_notifier import EmailNotifier
        n = EmailNotifier({"enabled": False})
        result = await n.send_alert({"level": "high", "message": "test"})
        assert result is False


# ── Webhook 测试 ──

class TestWebhookNotifier:
    def test_init(self):
        from backend.notifiers.webhook import WebhookNotifier
        n = WebhookNotifier({"enabled": True, "webhook_url": "https://test.com/hook"})
        assert n.enabled is True

    @pytest.mark.asyncio
    async def test_send_disabled(self):
        from backend.notifiers.webhook import WebhookNotifier
        n = WebhookNotifier({"enabled": False})
        result = await n.send_alert({"level": "high", "message": "test"})
        assert result is False
