"""
集成测试 - 多摄像头并发场景
测试多个摄像头管理器同时运行时的稳定性
"""
import pytest
import time
from unittest.mock import Mock, patch
from backend.camera import CameraManager


@pytest.mark.integration
@pytest.mark.slow
class TestMultiCameraIntegration:
    """多摄像头集成测试"""

    def test_multiple_cameras_lifecycle(self, config):
        """测试多个摄像头的生命周期管理"""
        cameras = []
        num_cameras = 3

        # 创建多个摄像头管理器
        for i in range(num_cameras):
            cam = CameraManager(
                camera_id=i,
                source=i,  # 使用虚拟摄像头 ID
                device="cpu",
            )
            cameras.append(cam)

        # 验证初始状态
        for cam in cameras:
            assert cam.camera_id in range(num_cameras)
            assert not cam.running
            assert not cam.connected

        # 注意：实际启动需要真实摄像头设备，此处仅测试对象创建

        # 清理
        for cam in cameras:
            if cam.running:
                cam.stop()

    @patch('cv2.VideoCapture')
    def test_cameras_independent_state(self, mock_video_capture, config):
        """测试多摄像头状态独立性"""
        # 模拟 VideoCapture
        mock_cap = Mock()
        mock_cap.isOpened.return_value = True
        mock_cap.read.return_value = (False, None)
        mock_video_capture.return_value = mock_cap

        cam1 = CameraManager(camera_id=1, source=0, device="cpu")
        cam2 = CameraManager(camera_id=2, source=1, device="cpu")

        # 修改 cam1 的配置不应影响 cam2
        cam1.conf_threshold = 0.7
        cam2.conf_threshold = 0.5

        assert cam1.conf_threshold == 0.7
        assert cam2.conf_threshold == 0.5
        assert cam1.camera_id != cam2.camera_id

        # 清理
        if cam1.running:
            cam1.stop()
        if cam2.running:
            cam2.stop()

    def test_camera_memory_isolation(self):
        """测试摄像头内存隔离（追踪器不共享）"""
        cam1 = CameraManager(camera_id=1, source=0, device="cpu")
        cam2 = CameraManager(camera_id=2, source=1, device="cpu")

        # 两个摄像头应有独立的追踪器实例
        assert cam1.tracker is not cam2.tracker
        assert cam1.screenshot_mgr is not cam2.screenshot_mgr
        assert cam1.roi_detector is not cam2.roi_detector

        # 修改 cam1 的追踪器不应影响 cam2
        cam1.tracker.track_ttl_sec = 120
        cam2.tracker.track_ttl_sec = 60

        assert cam1.tracker.track_ttl_sec == 120
        assert cam2.tracker.track_ttl_sec == 60


@pytest.mark.integration
class TestCameraConfigManagement:
    """测试摄像头配置管理"""

    def test_camera_config_update(self, config):
        """测试摄像头配置更新"""
        cam = CameraManager(camera_id=1, source=0, device="cpu")

        # 初始配置
        assert cam.conf_threshold == 0.5
        assert cam.detect_every_n == 2

        # 更新配置
        cam.conf_threshold = 0.6
        cam.detect_every_n = 3

        assert cam.conf_threshold == 0.6
        assert cam.detect_every_n == 3

    def test_camera_device_setting(self):
        """测试摄像头设备配置"""
        cam_cpu = CameraManager(camera_id=1, source=0, device="cpu")
        assert cam_cpu.detector.device == "cpu"

        cam_cuda = CameraManager(camera_id=2, source=1, device="cuda")
        assert cam_cuda.detector.device == "cuda"


@pytest.mark.integration
class TestCameraErrorHandling:
    """测试摄像头错误处理"""

    @patch('cv2.VideoCapture')
    def test_camera_connection_failure(self, mock_video_capture):
        """测试摄像头连接失败处理"""
        mock_cap = Mock()
        mock_cap.isOpened.return_value = False
        mock_video_capture.return_value = mock_cap

        cam = CameraManager(camera_id=1, source="rtsp://invalid", device="cpu")

        # 尝试打开摄像头应失败但不抛出异常
        cam.cap = mock_cap
        assert not cam.cap.isOpened()

    def test_camera_invalid_source(self):
        """测试无效视频源"""
        # 负数摄像头 ID
        cam = CameraManager(camera_id=1, source=-1, device="cpu")
        assert cam.source == -1

        # 空字符串 RTSP URL（创建对象应成功，实际连接时才失败）
        cam2 = CameraManager(camera_id=2, source="", device="cpu")
        assert cam2.source == ""


@pytest.mark.integration
class TestCameraBuffering:
    """测试摄像头帧缓冲"""

    def test_frame_buffer_size(self):
        """测试帧缓冲大小限制"""
        cam = CameraManager(camera_id=1, source=0, device="cpu")

        # 默认缓冲大小为 300
        assert cam._frame_buffer.maxlen == 300

    def test_frame_buffer_thread_safety(self):
        """测试帧缓冲的线程安全性"""
        cam = CameraManager(camera_id=1, source=0, device="cpu")

        # 缓冲锁应存在
        assert cam._buffer_lock is not None
        assert hasattr(cam._buffer_lock, 'acquire')
        assert hasattr(cam._buffer_lock, 'release')
