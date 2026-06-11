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


# ── SSRF 防护回归测试 ──

class TestWebhookSSRFProtection:
    """webhook URL 必须拒绝内网/回环/元数据地址"""

    @pytest.mark.parametrize("url", [
        "http://127.0.0.1/hook",
        "http://localhost:8080/hook",
        "http://10.0.0.5/hook",
        "http://192.168.1.100/hook",
        "http://172.16.0.1/hook",
        "http://169.254.169.254/latest/meta-data/",  # AWS/GCP 元数据
        "http://metadata.google.internal/",
        "ftp://example.com/hook",                     # 非 http(s)
        "file:///etc/passwd",
    ])
    def test_unsafe_url_disables_channel(self, url):
        from backend.notifiers.webhook import WebhookNotifier
        n = WebhookNotifier({"enabled": True, "webhook_url": url})
        assert n.enabled is False, f"应当拒绝危险 URL: {url}"

    def test_safe_public_url_passes(self):
        from backend.notifiers.webhook import WebhookNotifier
        n = WebhookNotifier({"enabled": True, "webhook_url": "https://hooks.slack.com/services/abc"})
        assert n.enabled is True

    def test_allow_private_url_opt_in(self):
        """显式 opt-in 时允许内网 URL（受控场景）"""
        from backend.notifiers.webhook import WebhookNotifier
        n = WebhookNotifier({
            "enabled": True,
            "webhook_url": "http://10.0.0.5/internal-hook",
            "allow_private_url": True,
        })
        assert n.enabled is True

    @pytest.mark.asyncio
    async def test_custom_headers_cannot_override_content_type(self):
        """用户 headers 不能顶掉 Content-Type: application/json"""
        from backend.notifiers.webhook import WebhookNotifier
        n = WebhookNotifier({
            "enabled": True,
            "webhook_url": "https://hooks.slack.com/services/abc",
            "headers": {"Content-Type": "text/plain", "X-Custom": "v"},
        })
        captured = {}

        class _Resp:
            status = 200
            async def __aenter__(self): return self
            async def __aexit__(self, *a): return False

        class _Session:
            async def __aenter__(self): return self
            async def __aexit__(self, *a): return False
            def post(self, url, **kwargs):
                captured["headers"] = kwargs.get("headers")
                return _Resp()

        with patch("aiohttp.ClientSession", return_value=_Session()):
            await n.send_alert({"level": "high", "message": "x"})

        assert captured["headers"]["Content-Type"] == "application/json"
        assert captured["headers"]["X-Custom"] == "v"


# ── 邮件头注入回归测试 ──

class TestEmailHeaderInjection:
    """Subject/收件人不得保留 CR/LF；HTML body 必须 escape 用户输入"""

    def test_sanitize_header_strips_crlf(self):
        from backend.notifiers.email_notifier import _sanitize_header
        assert "\r" not in _sanitize_header("foo\r\nBcc: attacker@evil.com")
        assert "\n" not in _sanitize_header("foo\r\nBcc: attacker@evil.com")
        assert "Bcc" in _sanitize_header("foo\r\nBcc: attacker@evil.com")  # 文本保留，但已折叠成单行

    @pytest.mark.asyncio
    async def test_send_alert_escapes_subject_and_body(self):
        from backend.notifiers.email_notifier import EmailNotifier
        n = EmailNotifier({
            "enabled": True,
            "smtp_host": "smtp.example.com",
            "to_addrs": ["a@b.com"],
            "smtp_user": "x", "smtp_password": "y",
            "from_addr": "from@b.com",
        })
        captured = {}

        def fake_send(subject, body):
            captured["subject"] = subject
            captured["body"] = body
            return True

        n._send_sync = fake_send
        alert = {
            "level": "high",
            "camera_id": 1,
            "timestamp": "2026-01-01",
            "message": "evil\r\nBcc: attacker@evil.com\r\n<script>x</script>",
            "data": {"person_count": 2},
        }
        await n.send_alert(alert)
        # subject 不能包含 CR/LF
        assert "\r" not in captured["subject"]
        assert "\n" not in captured["subject"]
        # body 中 <script> 应被转义
        assert "<script>" not in captured["body"]
        assert "&lt;script&gt;" in captured["body"]
