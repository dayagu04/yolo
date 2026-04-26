"""
飞书推送快速测试脚本
"""
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from backend.config import load_and_validate_config
from scripts.function import FeishuAPI, build_text_content, build_alert_card
from datetime import datetime


async def test_feishu():
    """测试飞书推送"""
    print("=" * 60)
    print("飞书推送功能测试")
    print("=" * 60)

    # 加载配置
    print("\n[1/4] 加载配置...")
    try:
        config = load_and_validate_config(ROOT / "config.yaml")
        feishu_cfg = config.get("notifications", {}).get("feishu", {})

        if not feishu_cfg.get("enabled"):
            print("❌ 飞书推送未启用，请在 config.yaml 中设置 notifications.feishu.enabled: true")
            return

        app_id = feishu_cfg.get("app_id")
        app_secret = feishu_cfg.get("app_secret")

        if not app_id or not app_secret:
            print("❌ 缺少飞书凭证，请在 config.secrets.yaml 中配置 app_id 和 app_secret")
            return

        print(f"✓ 配置加载成功")
        print(f"  App ID: {app_id[:10]}...")
    except Exception as e:
        print(f"❌ 配置加载失败: {e}")
        return

    # 初始化 API
    print("\n[2/4] 获取访问令牌...")
    try:
        api = FeishuAPI(app_id, app_secret)
        token = await api.get_tenant_token()
        if token:
            print(f"✓ Token 获取成功: {token[:20]}...")
        else:
            print("❌ Token 获取失败")
            return
    except Exception as e:
        print(f"❌ Token 获取失败: {e}")
        return

    # 发送文本消息
    print("\n[3/4] 发送文本消息...")
    try:
        content = build_text_content(
            f"🤖 系统测试消息\n"
            f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"状态: 飞书推送功能正常"
        )
        result = await api.send_message(
            receive_id="71ge4f55",
            msg_type="text",
            content=content,
            receive_id_type="open_id"
        )
        if result.get("code") == 0:
            msg_id = result.get("data", {}).get("message_id", "N/A")
            print(f"✓ 文本消息发送成功")
            print(f"  消息 ID: {msg_id}")
        else:
            print(f"❌ 文本消息发送失败: {result.get('msg')}")
            print(f"  详情: {result}")
    except Exception as e:
        print(f"❌ 文本消息发送失败: {e}")

    # 发送告警卡片
    print("\n[4/4] 发送告警卡片...")
    try:
        card = build_alert_card(
            camera_id=0,
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            person_count=3,
            new_count=1,
            message="系统测试：告警卡片推送功能正常"
        )
        result = await api.send_message(
            receive_id="71ge4f55",
            msg_type="interactive",
            content=card,
            receive_id_type="open_id"
        )
        if result.get("code") == 0:
            msg_id = result.get("data", {}).get("message_id", "N/A")
            print(f"✓ 告警卡片发送成功")
            print(f"  消息 ID: {msg_id}")
        else:
            print(f"❌ 告警卡片发送失败: {result.get('msg')}")
            print(f"  详情: {result}")
    except Exception as e:
        print(f"❌ 告警卡片发送失败: {e}")

    print("\n" + "=" * 60)
    print("测试完成！请检查飞书是否收到消息")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test_feishu())
