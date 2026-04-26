"""
Notifier 模块单元测试
"""
import pytest
from unittest.mock import Mock, patch, AsyncMock
from pathlib import Path
import sys

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from backend.notifier import FeishuNotifier


@pytest.mark.unit
class TestFeishuNotifier:
    """FeishuNotifier 单元测试"""

    @pytest.fixture
    def notifier_config(self):
        return {
            "enabled": True,
            "app_id": "test_app_id",
            "app_secret": "test_app_secret",
            "webhook_url": "https://test.webhook.url",
            "user_open_ids": ["user1", "user2"],
            "push_level": "high",
            "push_cooldown_sec": 0,  # 禁用冷却以便测试
        }

    @pytest.fixture
    def mock_alert(self):
        return {
            "camera_id": 0,
            "timestamp": "2026-04-26T15:00:00",
            "level": "high",
            "message": "检测到新人员",
            "data": {
                "person_count": 3,
                "new_track_ids": [1, 2],
            }
        }

    def test_notifier_init(self, notifier_config):
        """测试通知器初始化"""
        notifier = FeishuNotifier(notifier_config)

        assert notifier.enabled is True
        assert notifier.app_id == "test_app_id"
        assert notifier.app_secret == "test_app_secret"

    def test_notifier_disabled(self):
        """测试禁用通知器"""
        config = {"enabled": False}
        notifier = FeishuNotifier(config)

        assert notifier.enabled is False

    def test_notifier_default_values(self):
        """测试默认值"""
        config = {"enabled": True}
        notifier = FeishuNotifier(config)

        assert notifier.app_id == ""
        assert notifier.app_secret == ""
        assert notifier.webhook_url == ""
        assert notifier.user_open_ids == []
        assert notifier.push_level == "high"

    def test_should_push_level_high(self, notifier_config):
        """测试高级别告警推送判断"""
        notifier = FeishuNotifier(notifier_config)
        notifier.push_level = "high"

        assert notifier._should_push_level("high") is True
        assert notifier._should_push_level("medium") is False
        assert notifier._should_push_level("low") is False

    def test_should_push_level_medium(self, notifier_config):
        """测试中级别告警推送判断"""
        notifier = FeishuNotifier(notifier_config)
        notifier.push_level = "medium"

        assert notifier._should_push_level("high") is True
        assert notifier._should_push_level("medium") is True
        assert notifier._should_push_level("low") is False

    def test_should_push_level_low(self, notifier_config):
        """测试低级别告警推送判断"""
        notifier = FeishuNotifier(notifier_config)
        notifier.push_level = "low"

        assert notifier._should_push_level("high") is True
        assert notifier._should_push_level("medium") is True
        assert notifier._should_push_level("low") is True

    @pytest.mark.asyncio
    async def test_send_alert_disabled(self, mock_alert):
        """测试禁用时不发送告警"""
        config = {"enabled": False}
        notifier = FeishuNotifier(config)

        # 不应该抛出异常
        await notifier.send_alert(mock_alert)

    @pytest.mark.asyncio
    async def test_send_alert_low_level_filtered(self, notifier_config, mock_alert):
        """测试低级别告警被过滤"""
        notifier = FeishuNotifier(notifier_config)
        notifier.push_level = "high"
        mock_alert["level"] = "low"

        with patch.object(notifier, '_send_webhook', new_callable=AsyncMock) as mock_webhook:
            await notifier.send_alert(mock_alert)
            mock_webhook.assert_not_called()

    @pytest.mark.asyncio
    async def test_send_alert_cooldown(self, notifier_config, mock_alert):
        """测试推送冷却控制"""
        notifier_config["push_cooldown_sec"] = 60
        notifier = FeishuNotifier(notifier_config)
        import time
        notifier._last_push_ts = time.time()  # 刚刚推送过

        with patch.object(notifier, '_send_webhook', new_callable=AsyncMock) as mock_webhook:
            await notifier.send_alert(mock_alert)
            mock_webhook.assert_not_called()

    @pytest.mark.asyncio
    @patch('aiohttp.ClientSession.post')
    async def test_send_webhook_success(self, mock_post, notifier_config, mock_alert):
        """测试 Webhook 发送成功"""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=False)
        mock_post.return_value.__aenter__ = AsyncMock(return_value=mock_response)
        mock_post.return_value.__aexit__ = AsyncMock(return_value=False)

        notifier = FeishuNotifier(notifier_config)
        # 不应该抛出异常
        await notifier._send_webhook(mock_alert, None)

    @pytest.mark.asyncio
    @patch('aiohttp.ClientSession.post')
    async def test_send_webhook_failure_retries(self, mock_post, notifier_config, mock_alert):
        """测试 Webhook 失败时重试"""
        mock_response = AsyncMock()
        mock_response.status = 500
        mock_response.text = AsyncMock(return_value="Internal Server Error")
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=False)
        mock_post.return_value.__aenter__ = AsyncMock(return_value=mock_response)
        mock_post.return_value.__aexit__ = AsyncMock(return_value=False)

        notifier = FeishuNotifier(notifier_config)

        with patch('asyncio.sleep', new_callable=AsyncMock):
            await notifier._send_webhook(mock_alert, None)

        # 应该重试 2 次
        assert mock_post.call_count == 2

    @pytest.mark.asyncio
    async def test_get_tenant_token_cached(self, notifier_config):
        """测试使用缓存的 token"""
        notifier = FeishuNotifier(notifier_config)
        notifier._tenant_token = "cached_token"
        notifier._token_expire_ts = 9999999999  # 未来时间

        token = await notifier._get_tenant_token()

        assert token == "cached_token"

    @pytest.mark.asyncio
    async def test_get_tenant_token_expired(self, notifier_config):
        """测试 token 过期后重新获取"""
        notifier = FeishuNotifier(notifier_config)
        notifier._tenant_token = "old_token"
        notifier._token_expire_ts = 0  # 已过期

        with patch('aiohttp.ClientSession.post') as mock_post:
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.json = AsyncMock(return_value={
                "code": 0,
                "tenant_access_token": "new_token",
                "expire": 7200
            })
            mock_response.__aenter__ = AsyncMock(return_value=mock_response)
            mock_response.__aexit__ = AsyncMock(return_value=False)
            mock_post.return_value.__aenter__ = AsyncMock(return_value=mock_response)
            mock_post.return_value.__aexit__ = AsyncMock(return_value=False)

            token = await notifier._get_tenant_token()

            assert token == "new_token"
            assert notifier._tenant_token == "new_token"

    @pytest.mark.asyncio
    async def test_get_tenant_token_api_error(self, notifier_config):
        """测试获取 token API 错误"""
        notifier = FeishuNotifier(notifier_config)
        notifier._tenant_token = None
        notifier._token_expire_ts = 0

        with patch('aiohttp.ClientSession.post') as mock_post:
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.json = AsyncMock(return_value={"code": 99, "msg": "error"})
            mock_response.__aenter__ = AsyncMock(return_value=mock_response)
            mock_response.__aexit__ = AsyncMock(return_value=False)
            mock_post.return_value.__aenter__ = AsyncMock(return_value=mock_response)
            mock_post.return_value.__aexit__ = AsyncMock(return_value=False)

            token = await notifier._get_tenant_token()

            assert token is None

    @pytest.mark.asyncio
    async def test_upload_image_file_not_found(self, notifier_config):
        """测试上传不存在的图片"""
        notifier = FeishuNotifier(notifier_config)
        notifier._tenant_token = "test_token"
        notifier._token_expire_ts = 9999999999

        image_key = await notifier._upload_image("nonexistent.jpg")

        assert image_key is None

    @pytest.mark.asyncio
    async def test_upload_image_no_token(self, notifier_config):
        """测试无 token 时上传图片"""
        notifier = FeishuNotifier(notifier_config)
        notifier._tenant_token = None
        notifier._token_expire_ts = 0

        with patch.object(notifier, '_get_tenant_token', new_callable=AsyncMock, return_value=None):
            image_key = await notifier._upload_image("some_file.jpg")

        assert image_key is None

    @pytest.mark.asyncio
    async def test_build_card_basic(self, notifier_config, mock_alert):
        """测试构建基本告警卡片"""
        notifier = FeishuNotifier(notifier_config)

        card = await notifier._build_card(mock_alert, None)

        assert "msg_type" in card
        assert card["msg_type"] == "interactive"
        assert "card" in card
        assert "header" in card["card"]
        assert "elements" in card["card"]

    @pytest.mark.asyncio
    async def test_build_card_with_screenshot(self, notifier_config, mock_alert, tmp_path):
        """测试构建带截图的卡片"""
        import cv2
        import numpy as np

        img = np.zeros((100, 100, 3), dtype=np.uint8)
        img_path = tmp_path / "test.jpg"
        cv2.imwrite(str(img_path), img)

        notifier = FeishuNotifier(notifier_config)
        notifier._tenant_token = "test_token"
        notifier._token_expire_ts = 9999999999

        with patch.object(notifier, '_upload_image', new_callable=AsyncMock, return_value="test_image_key"):
            card = await notifier._build_card(mock_alert, str(img_path))

            card_str = str(card)
            assert "test_image_key" in card_str

    @pytest.mark.asyncio
    async def test_build_card_no_screenshot(self, notifier_config, mock_alert):
        """测试构建无截图的卡片"""
        notifier = FeishuNotifier(notifier_config)

        card = await notifier._build_card(mock_alert, None)

        # 不应该有图片元素
        elements = card["card"]["elements"]
        has_img = any(e.get("tag") == "img" for e in elements)
        assert has_img is False

    @pytest.mark.boundary
    def test_empty_user_list(self):
        """测试空用户列表"""
        config = {
            "enabled": True,
            "app_id": "test",
            "app_secret": "test",
            "user_open_ids": []
        }
        notifier = FeishuNotifier(config)

        assert notifier.user_open_ids == []

    @pytest.mark.boundary
    def test_missing_config_fields(self):
        """测试缺少配置字段"""
        config = {"enabled": True}
        notifier = FeishuNotifier(config)

        assert notifier.app_id == ""

    @pytest.mark.exception
    @pytest.mark.asyncio
    async def test_network_error_in_send_alert(self, notifier_config, mock_alert):
        """测试 send_alert 中的网络错误"""
        notifier = FeishuNotifier(notifier_config)

        with patch.object(notifier, '_send_webhook', side_effect=Exception("Network error")):
            # 不应该抛出异常（gather 会捕获）
            await notifier.send_alert(mock_alert)

    @pytest.mark.exception
    @pytest.mark.asyncio
    async def test_get_tenant_token_network_error(self, notifier_config):
        """测试获取 token 时网络错误"""
        notifier = FeishuNotifier(notifier_config)
        notifier._tenant_token = None
        notifier._token_expire_ts = 0

        with patch('aiohttp.ClientSession.post', side_effect=Exception("Network error")):
            token = await notifier._get_tenant_token()

        assert token is None
