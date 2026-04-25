"""
飞书消息功能函数库
提供发送消息、回复消息、上传图片等基础能力
"""
import json
import aiohttp
from typing import Optional, Dict, Any, List
from pathlib import Path


class FeishuAPI:
    """飞书 OpenAPI 封装"""

    BASE_URL = "https://open.feishu.cn/open-apis"

    def __init__(self, app_id: str, app_secret: str):
        self.app_id = app_id
        self.app_secret = app_secret
        self._token: Optional[str] = None
        self._token_expire: float = 0.0

    async def get_tenant_token(self) -> str:
        """获取 tenant_access_token"""
        import time
        now = time.time()

        if self._token and now < self._token_expire:
            return self._token

        url = f"{self.BASE_URL}/auth/v3/tenant_access_token/internal"
        payload = {"app_id": self.app_id, "app_secret": self.app_secret}

        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, timeout=10) as resp:
                data = await resp.json()
                if data.get("code") == 0:
                    self._token = data["tenant_access_token"]
                    self._token_expire = now + data.get("expire", 7200) - 300
                    return self._token
                else:
                    raise Exception(f"获取 token 失败: {data}")

    async def send_message(
        self,
        receive_id: str,
        msg_type: str,
        content: Dict[str, Any],
        receive_id_type: str = "open_id",
        uuid: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        发送消息
        Args:
            receive_id: 接收者 ID
            msg_type: 消息类型 (text/post/image/interactive等)
            content: 消息内容字典
            receive_id_type: ID类型 (open_id/user_id/chat_id等)
            uuid: 去重ID
        Returns:
            响应数据
        """
        token = await self.get_tenant_token()
        url = f"{self.BASE_URL}/im/v1/messages"
        params = {"receive_id_type": receive_id_type}
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=utf-8"
        }
        payload = {
            "receive_id": receive_id,
            "msg_type": msg_type,
            "content": json.dumps(content, ensure_ascii=False)
        }
        if uuid:
            payload["uuid"] = uuid

        async with aiohttp.ClientSession() as session:
            async with session.post(url, params=params, headers=headers, json=payload, timeout=10) as resp:
                return await resp.json()

    async def reply_message(
        self,
        message_id: str,
        msg_type: str,
        content: Dict[str, Any],
        reply_in_thread: bool = False,
        uuid: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        回复消息
        Args:
            message_id: 待回复的消息ID
            msg_type: 消息类型
            content: 消息内容字典
            reply_in_thread: 是否以话题形式回复
            uuid: 去重ID
        Returns:
            响应数据
        """
        token = await self.get_tenant_token()
        url = f"{self.BASE_URL}/im/v1/messages/{message_id}/reply"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=utf-8"
        }
        payload = {
            "msg_type": msg_type,
            "content": json.dumps(content, ensure_ascii=False),
            "reply_in_thread": reply_in_thread
        }
        if uuid:
            payload["uuid"] = uuid

        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=payload, timeout=10) as resp:
                return await resp.json()

    async def upload_image(self, image_path: str) -> Optional[str]:
        """
        上传图片
        Args:
            image_path: 图片文件路径
        Returns:
            image_key (成功) 或 None (失败)
        """
        token = await self.get_tenant_token()
        url = f"{self.BASE_URL}/im/v1/images"
        headers = {"Authorization": f"Bearer {token}"}

        file_path = Path(image_path)
        if not file_path.exists():
            raise FileNotFoundError(f"图片文件不存在: {image_path}")

        form = aiohttp.FormData()
        form.add_field("image_type", "message")
        form.add_field("image", open(file_path, "rb"), filename=file_path.name)

        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, data=form, timeout=30) as resp:
                data = await resp.json()
                if data.get("code") == 0:
                    return data["data"]["image_key"]
                else:
                    raise Exception(f"上传图片失败: {data}")

    async def upload_file(self, file_path: str, file_type: str = "stream") -> Optional[str]:
        """
        上传文件
        Args:
            file_path: 文件路径
            file_type: 文件类型 (stream/opus/mp4/pdf/doc等)
        Returns:
            file_key (成功) 或 None (失败)
        """
        token = await self.get_tenant_token()
        url = f"{self.BASE_URL}/im/v1/files"
        headers = {"Authorization": f"Bearer {token}"}

        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"文件不存在: {file_path}")

        form = aiohttp.FormData()
        form.add_field("file_type", file_type)
        form.add_field("file_name", path.name)
        form.add_field("file", open(path, "rb"), filename=path.name)

        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, data=form, timeout=60) as resp:
                data = await resp.json()
                if data.get("code") == 0:
                    return data["data"]["file_key"]
                else:
                    raise Exception(f"上传文件失败: {data}")


# ============================================================
# 辅助函数：快速构建消息内容
# ============================================================

def build_text_content(text: str) -> Dict[str, str]:
    """构建文本消息内容"""
    return {"text": text}


def build_image_content(image_key: str) -> Dict[str, str]:
    """构建图片消息内容"""
    return {"image_key": image_key}


def build_card_content(
    title: str,
    content: str,
    template: str = "blue",
    elements: Optional[List[Dict]] = None
) -> Dict[str, Any]:
    """
    构建卡片消息内容
    Args:
        title: 卡片标题
        content: 卡片内容（支持 Markdown）
        template: 卡片模板颜色 (blue/red/green/yellow等)
        elements: 额外的卡片元素列表
    """
    card = {
        "header": {
            "title": {"tag": "plain_text", "content": title},
            "template": template
        },
        "elements": [
            {"tag": "div", "text": {"tag": "lark_md", "content": content}}
        ]
    }
    if elements:
        card["elements"].extend(elements)
    return card


def build_alert_card(
    camera_id: int,
    timestamp: str,
    person_count: int,
    new_count: int,
    message: str,
    image_key: Optional[str] = None
) -> Dict[str, Any]:
    """构建告警卡片"""
    content = f"**摄像头**: {camera_id}\n"
    content += f"**时间**: {timestamp}\n"
    content += f"**人数**: {person_count} 人\n"
    content += f"**新增**: {new_count} 人\n"
    content += f"**消息**: {message}"

    card = build_card_content("⚠️ 安防告警", content, template="red")

    if image_key:
        card["elements"].append({
            "tag": "img",
            "img_key": image_key,
            "alt": {"tag": "plain_text", "content": "告警截图"}
        })

    return card


# ============================================================
# 使用示例
# ============================================================

async def example_send_text():
    """示例：发送文本消息"""
    api = FeishuAPI(app_id="your_app_id", app_secret="your_app_secret")
    content = build_text_content("这是一条测试消息")
    result = await api.send_message(
        receive_id="ou_xxxxxx",
        msg_type="text",
        content=content,
        receive_id_type="open_id"
    )
    print(result)


async def example_send_alert_with_image():
    """示例：发送带截图的告警卡片"""
    api = FeishuAPI(app_id="your_app_id", app_secret="your_app_secret")

    image_key = await api.upload_image("data/screenshots/2026-04-25/alert_001.jpg")

    card = build_alert_card(
        camera_id=0,
        timestamp="2026-04-25 14:30:00",
        person_count=3,
        new_count=1,
        message="检测到新人员进入",
        image_key=image_key
    )

    result = await api.send_message(
        receive_id="oc_xxxxxx",
        msg_type="interactive",
        content=card,
        receive_id_type="chat_id"
    )
    print(result)


async def example_reply_message():
    """示例：回复消息"""
    api = FeishuAPI(app_id="your_app_id", app_secret="your_app_secret")
    content = build_text_content("已收到告警，正在处理")
    result = await api.reply_message(
        message_id="om_xxxxxx",
        msg_type="text",
        content=content,
        reply_in_thread=False
    )
    print(result)
