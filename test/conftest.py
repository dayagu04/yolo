"""
Pytest 配置和共享 fixtures
"""
import pytest
import asyncio
import subprocess
import time
import sys
from pathlib import Path

# 添加项目根目录到路径
ROOT = Path(__file__).parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.config import load_and_validate_config
from backend.database import DatabaseManager
from backend.redis_stats import RedisStats


@pytest.fixture(scope="session")
def event_loop():
    """创建事件循环"""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
def config():
    """加载配置"""
    return load_and_validate_config(ROOT / "config.yaml")


@pytest.fixture(scope="session")
def backend_server():
    """启动后端服务"""
    import requests
    import os

    print("\n启动后端服务...")

    # 使用测试配置（禁用摄像头自动启动）
    env = os.environ.copy()
    env["CONFIG_FILE"] = "config.test.yaml"

    process = subprocess.Popen(
        [sys.executable, "backend/main.py"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=ROOT,
        env=env
    )

    # 健康检查等待（最多30秒）
    start = time.time()
    ready = False
    while time.time() - start < 30:
        try:
            resp = requests.get("http://localhost:8000/health", timeout=2)
            if resp.status_code == 200:
                ready = True
                break
        except Exception:
            pass
        time.sleep(1)

    if not ready:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
        raise RuntimeError("后端服务启动超时")

    print("后端服务已启动（使用测试配置，摄像头按需启动）")

    # 预热摄像头（让摄像头提前初始化，避免测试时超时）
    print("预热摄像头...")
    try:
        resp = requests.get("http://localhost:8000/api/camera/0/status", timeout=30)
        if resp.status_code == 200:
            print("摄像头预热完成")
        else:
            print(f"摄像头预热失败: HTTP {resp.status_code}")
    except Exception as e:
        print(f"摄像头预热异常: {e}")
        print("警告: 摄像头可能不可用，相关测试可能失败")

    yield process

    # 测试完成后停止服务
    print("\n停止后端服务...")
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        print("后端服务未响应，强制终止...")
        process.kill()
        process.wait()

    # 额外等待，确保摄像头资源释放
    time.sleep(2)
    print("后端服务已停止，资源已释放")


@pytest.fixture(scope="session")
def base_url():
    """后端服务地址"""
    return "http://localhost:8000"


@pytest.fixture(scope="function")
def db_manager(config):
    """数据库管理器（每个测试函数独立）"""
    db = DatabaseManager(config["database"])
    yield db
    # 测试后清理
    db.engine.dispose()


@pytest.fixture(scope="function")
def redis_stats(config):
    """Redis 统计（每个测试函数独立）"""
    redis_cfg = config.get("redis", {})
    if redis_cfg.get("enabled"):
        redis = RedisStats(redis_cfg)
        yield redis
    else:
        yield None


@pytest.fixture(scope="session", autouse=True)
def setup_teardown():
    """全局设置和清理"""
    print("\n" + "=" * 100)
    print("开始测试")
    print("=" * 100)

    yield

    print("\n" + "=" * 100)
    print("测试完成")
    print("=" * 100)


@pytest.fixture
def temp_screenshot(tmp_path):
    """创建临时截图文件"""
    import cv2
    import numpy as np

    # 创建测试图片
    img = np.zeros((480, 640, 3), dtype=np.uint8)
    cv2.putText(img, "Test Screenshot", (50, 240),
                cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)

    img_path = tmp_path / "test_screenshot.jpg"
    cv2.imwrite(str(img_path), img)

    return str(img_path)
