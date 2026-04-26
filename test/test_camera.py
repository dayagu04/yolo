"""
摄像头功能测试模块
"""
import pytest
import requests
import time
from pathlib import Path

ROOT = Path(__file__).parent.parent


@pytest.mark.camera
@pytest.mark.usefixtures("backend_server")
class TestCameraFunctions:
    """摄像头功能测试类"""

    def test_model_file_exists(self):
        """测试 YOLO 模型文件存在"""
        model_path = ROOT / "models" / "person_best.pt"
        assert model_path.exists(), "模型文件不存在"
        assert model_path.stat().st_size > 1024 * 1024, "模型文件太小"

    def test_camera_status_query(self, base_url):
        """测试摄像头状态查询"""
        resp = requests.get(f"{base_url}/api/camera/0/status", timeout=5)
        assert resp.status_code == 200

        data = resp.json()
        assert "connected" in data
        assert "detection_enabled" in data
        assert "fps" in data
        assert "model_loaded" in data

    def test_camera_connection(self, base_url):
        """测试摄像头连接状态"""
        resp = requests.get(f"{base_url}/api/camera/0/status", timeout=5)
        data = resp.json()

        # 摄像头应该已连接
        assert data.get("running") is True

    def test_detection_enabled(self, base_url):
        """测试检测功能启用"""
        resp = requests.get(f"{base_url}/api/camera/0/status", timeout=5)
        data = resp.json()

        assert data.get("detection_enabled") is True
        assert data.get("model_loaded") is True

    def test_fps_measurement(self, base_url):
        """测试 FPS 测量"""
        resp = requests.get(f"{base_url}/api/camera/0/status", timeout=5)
        data = resp.json()

        fps = data.get("fps", 0)
        assert fps > 0, "FPS 应该大于 0"
        assert fps < 100, "FPS 异常高"

    def test_video_stream(self, base_url):
        """测试视频流"""
        resp = requests.get(f"{base_url}/video_feed?camera_id=0",
                            timeout=3, stream=True)
        assert resp.status_code == 200

        # 验证 MJPEG 流格式
        chunk = next(resp.iter_content(1024), None)
        assert chunk is not None
        assert b"--frame" in chunk
        assert b"Content-Type: image/jpeg" in chunk

    def test_detection_config_update(self, base_url):
        """测试检测配置更新"""
        # 更新置信度阈值
        payload = {"enabled": True, "conf": 0.7}
        resp = requests.post(f"{base_url}/api/camera/0/config",
                             json=payload, timeout=5)
        assert resp.status_code == 200

        # 验证更新生效
        time.sleep(1)
        resp = requests.get(f"{base_url}/api/camera/0/status", timeout=5)
        data = resp.json()
        assert abs(data.get("conf_threshold", 0) - 0.7) < 0.01

    def test_disable_detection(self, base_url):
        """测试禁用检测"""
        payload = {"enabled": False}
        resp = requests.post(f"{base_url}/api/camera/0/config",
                             json=payload, timeout=5)
        assert resp.status_code == 200

        # 恢复启用
        payload = {"enabled": True}
        requests.post(f"{base_url}/api/camera/0/config",
                      json=payload, timeout=5)

    def test_camera_resolution(self, base_url):
        """测试摄像头分辨率"""
        resp = requests.get(f"{base_url}/api/camera/0/status", timeout=5)
        data = resp.json()

        resolution = data.get("resolution", "")
        assert "x" in resolution, "分辨率格式错误"

        width, height = map(int, resolution.split("x"))
        assert width > 0 and height > 0

    @pytest.mark.slow
    def test_camera_stability(self, base_url):
        """测试摄像头稳定性（30秒）"""
        start_time = time.time()
        errors = 0

        while time.time() - start_time < 30:
            try:
                resp = requests.get(f"{base_url}/api/camera/0/status", timeout=5)
                if resp.status_code != 200:
                    errors += 1
            except Exception:
                errors += 1

            time.sleep(1)

        assert errors < 3, f"30秒内出现 {errors} 次错误"

    @pytest.mark.boundary
    def test_invalid_conf_threshold(self, base_url):
        """测试无效置信度阈值"""
        # 超出范围
        payload = {"conf": 1.5}
        resp = requests.post(f"{base_url}/api/camera/0/config",
                             json=payload, timeout=5)
        # 应该返回错误或限制在有效范围
        assert resp.status_code in [200, 422]

    @pytest.mark.boundary
    def test_negative_conf_threshold(self, base_url):
        """测试负数置信度"""
        payload = {"conf": -0.5}
        resp = requests.post(f"{base_url}/api/camera/0/config",
                             json=payload, timeout=5)
        assert resp.status_code in [200, 422]

    @pytest.mark.exception
    def test_nonexistent_camera(self, base_url):
        """测试不存在的摄像头"""
        resp = requests.get(f"{base_url}/api/camera/999/status", timeout=5)
        # 可能创建新摄像头或返回错误
        assert resp.status_code in [200, 404, 500]

    @pytest.mark.performance
    def test_video_stream_performance(self, base_url):
        """测试视频流性能"""
        start = time.time()
        resp = requests.get(f"{base_url}/video_feed?camera_id=0",
                            timeout=5, stream=True)

        # 读取 10 帧
        frames = 0
        for chunk in resp.iter_content(chunk_size=8192):
            if b"--frame" in chunk:
                frames += 1
            if frames >= 10:
                break

        duration = time.time() - start
        fps = frames / duration

        assert fps > 5, f"视频流 FPS {fps:.1f} 太低"
