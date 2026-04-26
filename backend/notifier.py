"""
飞书告警推送模块
支持群机器人 Webhook 和直接消息（OpenAPI）
"""
import time
import asyncio
import logging
import json
import uuid
from typing import Optional, Dict, List
from pathlib import Path
import aiohttp

_TIMEOUT_SHORT = aiohttp.ClientTimeout(total=10)
_TIMEOUT_UPLOAD = aiohttp.ClientTimeout(total=30)


class FeishuNotifier:
    """飞书推送通知器"""

    def __init__(self, config: dict):
        self.config = config
        self.logger = logging.getLogger(__name__)

        # 配置参数
        self.enabled = config.get("enabled", False)
        self.app_id = config.get("app_id", "")
        self.app_secret = config.get("app_secret", "")
        self.webhook_url = config.get("webhook_url", "")
        self.receive_id_type = config.get("receive_id_type", "open_id")
        self.user_open_ids: List[str] = config.get("user_open_ids", [])

        # 推送控制
        self.push_cooldown_sec = config.get("push_cooldown_sec", 60)
        self.push_level = config.get("push_level", "high")
        self.include_screenshot = config.get("include_screenshot", True)

        # 截图根目录（绝对路径，用于上传时拼接相对路径）
        self._screenshots_root: Optional[Path] = None
        self._last_push_ts = 0.0
        self._tenant_token: Optional[str] = None
        self._token_expire_ts = 0.0

        if not self.enabled:
            self.logger.info("飞书推送未启用")
        elif not self.app_id or not self.app_secret:
            self.logger.warning("飞书推送已启用，但缺少 app_id 或 app_secret")

    async def send_alert(self, alert: dict, screenshot_path: Optional[str] = None):
        """
        发送告警推送
        Args:
            alert: 告警消息字典（AlertMessage.model_dump()）
            screenshot_path: 截图相对路径（可选）
        """
        if not self.enabled:
            return

        # 推送冷却控制
        now = time.time()
        if now - self._last_push_ts < self.push_cooldown_sec:
            return

        # 级别过滤
        alert_level = alert.get("level", "high")
        if not self._should_push_level(alert_level):
            return

        self._last_push_ts = now

        # 并发发送群消息和直接消息
        tasks = []
        if self.webhook_url:
            tasks.append(self._send_webhook(alert, screenshot_path))
        if self.app_id and self.user_open_ids:
            tasks.append(self._send_direct_messages(alert, screenshot_path))

        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    self.logger.error(f"飞书推送失败 (task {i}): {result}")

    def _should_push_level(self, alert_level: str) -> bool:
        """判断告警级别是否需要推送"""
        level_priority = {"low": 1, "medium": 2, "high": 3}
        return level_priority.get(alert_level, 3) >= level_priority.get(self.push_level, 3)

    async def _send_webhook(self, alert: dict, screenshot_path: Optional[str]):
        """发送群机器人 Webhook 消息（带重试）"""
        card = await self._build_card(alert, screenshot_path)

        for attempt in range(1, 3):  # 最多重试 2 次
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(self.webhook_url, json=card, timeout=_TIMEOUT_SHORT) as resp:
                        if resp.status == 200:
                            self.logger.info("飞书群消息推送成功")
                            return
                        else:
                            text = await resp.text()
                            self.logger.error(f"飞书群消息推送失败 (尝试 {attempt}/2): {resp.status} {text}")
            except Exception as e:
                self.logger.error(f"飞书群消息推送异常 (尝试 {attempt}/2): {e}")

            if attempt < 2:
                await asyncio.sleep(2 ** attempt)  # 指数退避: 2s, 4s

    async def _send_direct_messages(self, alert: dict, screenshot_path: Optional[str]):
        """发送直接消息给指定用户"""
        try:
            token = await self._get_tenant_token()
            if not token:
                return

            card = await self._build_card(alert, screenshot_path)
            async with aiohttp.ClientSession() as session:
                for open_id in self.user_open_ids:
                    await self._post_message(session, token, open_id, card)
        except Exception as e:
            self.logger.error(f"飞书直接消息推送异常: {e}")

    async def _get_tenant_token(self) -> Optional[str]:
        """获取 tenant_access_token（带缓存）"""
        now = time.time()
        if self._tenant_token and now < self._token_expire_ts:
            return self._tenant_token

        try:
            url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
            payload = {"app_id": self.app_id, "app_secret": self.app_secret}

            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, timeout=10) as resp:
                    data = await resp.json()
                    if data.get("code") == 0:
                        self._tenant_token = data["tenant_access_token"]
                        self._token_expire_ts = now + data.get("expire", 7200) - 300  # 提前 5 分钟刷新
                        return self._tenant_token
                    else:
                        self.logger.error(f"获取飞书 token 失败: {data}")
                        return None
        except Exception as e:
            self.logger.error(f"获取飞书 token 异常: {e}")
            return None

    async def _post_message(self, session: aiohttp.ClientSession, token: str, receive_id: str, card: dict):
        """发送消息给指定用户（带重试）"""
        url = "https://open.feishu.cn/open-apis/im/v1/messages"
        params = {"receive_id_type": self.receive_id_type}
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=utf-8",
        }

        content = json.dumps(card["card"], ensure_ascii=False)
        payload = {
            "receive_id": receive_id,
            "msg_type": "interactive",
            "content": content,
            "uuid": str(uuid.uuid4()),
        }

        for attempt in range(1, 3):  # 最多重试 2 次
            try:
                async with session.post(url, params=params, headers=headers, json=payload, timeout=10) as resp:
                    text = await resp.text()
                    if resp.status == 200:
                        try:
                            data = json.loads(text)
                        except Exception:
                            data = {}

                        if data.get("code") == 0:
                            self.logger.info(f"飞书直接消息推送成功: {self.receive_id_type}={receive_id}")
                            return

                        self.logger.error(f"飞书直接消息推送失败 ({self.receive_id_type}={receive_id}, 尝试 {attempt}/2): {data}")
                    else:
                        self.logger.error(f"飞书直接消息推送失败 ({self.receive_id_type}={receive_id}, 尝试 {attempt}/2): {resp.status} {text}")
            except Exception as e:
                self.logger.error(f"飞书直接消息推送异常 ({self.receive_id_type}={receive_id}, 尝试 {attempt}/2): {e}")

            if attempt < 2:
                await asyncio.sleep(2 ** attempt)

    async def _build_card(self, alert: dict, screenshot_path: Optional[str]) -> dict:
        """构建飞书卡片消息"""
        data = alert.get("data", {})
        camera_id = alert.get("camera_id", 0)
        timestamp = alert.get("timestamp", "")
        message = alert.get("message", "检测到人员")
        person_count = data.get("person_count", 0)
        new_track_ids = data.get("new_track_ids", [])

        # 卡片内容
        content = f"**摄像头**: {camera_id}\n"
        content += f"**时间**: {timestamp}\n"
        content += f"**人数**: {person_count} 人\n"
        content += f"**新增**: {len(new_track_ids)} 人\n"
        content += f"**消息**: {message}"

        card = {
            "msg_type": "interactive",
            "card": {
                "header": {
                    "title": {"tag": "plain_text", "content": "⚠️ 安防告警"},
                    "template": "red",
                },
                "elements": [
                    {
                        "tag": "div",
                        "text": {"tag": "lark_md", "content": content},
                    }
                ],
            },
        }

        # 截图上传
        if self.include_screenshot and screenshot_path:
            image_key = await self._upload_image(screenshot_path)
            if image_key:
                card["card"]["elements"].append({
                    "tag": "img",
                    "img_key": image_key,
                    "alt": {"tag": "plain_text", "content": "告警截图"}
                })

        return card

    async def _upload_image(self, image_path: str) -> Optional[str]:
        """上传图片到飞书，返回 image_key。
        image_path 可以是绝对路径，也可以是相对于 _screenshots_root 的相对路径。
        """
        token = await self._get_tenant_token()
        if not token:
            return None

        path = Path(image_path)
        # 相对路径时，拼接截图根目录
        if not path.is_absolute() and self._screenshots_root:
            path = self._screenshots_root / path

        if not path.exists():
            self.logger.warning(f"截图文件不存在: {path}")
            return None

        try:
            url = "https://open.feishu.cn/open-apis/im/v1/images"
            headers = {"Authorization": f"Bearer {token}"}
            form = aiohttp.FormData()
            form.add_field("image_type", "message")
            with open(path, "rb") as f:
                form.add_field("image", f, filename=path.name, content_type="image/jpeg")

                async with aiohttp.ClientSession() as session:
                    async with session.post(url, headers=headers, data=form, timeout=30) as resp:
                        data = await resp.json()
                        if data.get("code") == 0:
                            self.logger.info(f"飞书图片上传成功: {path.name}")
                            return data["data"]["image_key"]
                        else:
                            self.logger.error(f"飞书图片上传失败: {data}")
                            return None
        except Exception as e:
            self.logger.error(f"飞书图片上传异常: {e}")
            return None
