"""
Camera 模块单元测试
"""
import pytest
import numpy as np
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path
import sys

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from backend.camera import CameraManager


@pytest.mark.unit
class TestCameraManager:
    """CameraManager 单元测试"""

    @pytest.fixture
    def screenshot_config(self):
        return {
            "enabled": True,
            "save_mode": "first_only",
            "quality": 75,
            "save_dir": "data/screenshots"
        }

    @pytest.fixture
    def camera(self, screenshot_config):
        """创建 CameraManager 实例（不启动摄像头）"""
        return CameraManager(
            camera_id=0,
            source=0,
            screenshot_config=screenshot_config,
        )

    def test_camera_init(self, camera):
        """测试摄像头初始化"""
        assert camera.camera_id == 0
        assert camera.source == 0
        assert camera.detection_enabled is True
        assert camera.conf_threshold == 0.5
        assert camera.running is False
        assert camera.cap is None

    def test_iou_calculation(self):
        """测试 IoU 计算"""
        box1 = (0, 0, 10, 10)
        box2 = (5, 5, 15, 15)

        iou = CameraManager._iou(box1, box2)

        # 交集面积 = 5*5 = 25，并集面积 = 100 + 100 - 25 = 175
        assert 0.14 < iou < 0.15

    def test_iou_no_overlap(self):
        """测试无重叠的 IoU"""
        box1 = (0, 0, 10, 10)
        box2 = (20, 20, 30, 30)

        iou = CameraManager._iou(box1, box2)
        assert iou == 0.0

    def test_iou_complete_overlap(self):
        """测试完全重叠的 IoU"""
        box1 = (0, 0, 10, 10)
        box2 = (0, 0, 10, 10)

        iou = CameraManager._iou(box1, box2)
        assert iou == 1.0

    @patch('cv2.VideoCapture')
    def test_open_camera_success(self, mock_cv2, camera):
        """测试成功打开摄像头"""
        mock_cap = Mock()
        mock_cap.isOpened.return_value = True
        mock_cap.get.return_value = 640.0
        mock_cap.read.return_value = (True, np.zeros((480, 640, 3), dtype=np.uint8))
        mock_cv2.return_value = mock_cap

        result = camera._open_camera()

        assert result is True
        assert camera.cap is not None

    @patch('cv2.VideoCapture')
    def test_open_camera_failure(self, mock_cv2, camera):
        """测试打开摄像头失败"""
        mock_cap = Mock()
        mock_cap.isOpened.return_value = False
        mock_cv2.return_value = mock_cap

        result = camera._open_camera()

        assert result is False

    def test_close_camera(self, camera):
        """测试关闭摄像头"""
        mock_cap = Mock()
        camera.cap = mock_cap
        camera.connected = True

        camera._close_camera()

        mock_cap.release.assert_called_once()
        assert camera.cap is None
        assert camera.connected is False

    def test_get_status(self, camera):
        """测试获取状态"""
        camera.running = True
        camera.connected = True
        camera._model = Mock()
        camera._fps = 30.0
        camera.width = 640
        camera.height = 480

        status = camera.get_status()

        assert status["camera_id"] == 0
        assert status["running"] is True
        assert status["connected"] is True
        assert status["model_loaded"] is True
        assert status["fps"] == 30.0
        assert status["resolution"] == "640x480"

    def test_get_status_no_model(self, camera):
        """测试无模型时的状态"""
        status = camera.get_status()

        assert status["model_loaded"] is False
        assert status["running"] is False

    def test_associate_tracks_new_detection(self, camera):
        """测试新检测的 Track 关联"""
        boxes = [(10, 10, 50, 50)]
        now_ts = 1000.0

        track_ids = camera._associate_tracks(boxes, now_ts)

        assert len(track_ids) == 1
        assert len(camera._tracks) == 1

    def test_associate_tracks_existing_detection(self, camera):
        """测试已存在检测的 Track 关联"""
        boxes1 = [(10, 10, 50, 50)]
        track_ids1 = camera._associate_tracks(boxes1, 1000.0)

        # 位置略有变化
        boxes2 = [(12, 12, 52, 52)]
        track_ids2 = camera._associate_tracks(boxes2, 1001.0)

        # 应该关联到同一个 Track
        assert track_ids1[0] == track_ids2[0]
        assert len(camera._tracks) == 1

    def test_associate_tracks_expired(self, camera):
        """测试过期 Track 清理"""
        camera._track_ttl_sec = 5

        boxes1 = [(10, 10, 50, 50)]
        camera._associate_tracks(boxes1, 1000.0)

        # 6秒后再次检测（超过 TTL）
        boxes2 = [(10, 10, 50, 50)]
        camera._associate_tracks(boxes2, 1006.0)

        # 旧 Track 应该被清理，创建新 Track
        assert len(camera._tracks) == 1

    @patch('cv2.imwrite')
    def test_save_screenshot(self, mock_imwrite, camera, tmp_path):
        """测试保存截图"""
        camera.screenshot_config["save_dir"] = str(tmp_path)
        mock_imwrite.return_value = True

        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        path = camera._save_screenshot(frame)

        assert path is not None
        assert ".jpg" in path
        mock_imwrite.assert_called_once()

    def test_should_save_screenshot_first_only(self, camera):
        """测试首次截图模式"""
        camera.screenshot_config["save_mode"] = "first_only"
        camera._alert_total = 0

        assert camera._should_save_screenshot(1000.0) is True

        camera._alert_total = 1
        assert camera._should_save_screenshot(1001.0) is False

    def test_should_save_screenshot_all(self, camera):
        """测试全部截图模式"""
        camera.screenshot_config["save_mode"] = "all"

        assert camera._should_save_screenshot(1000.0) is True
        assert camera._should_save_screenshot(1001.0) is True

    def test_should_save_screenshot_interval(self, camera):
        """测试间隔截图模式"""
        camera.screenshot_config["save_mode"] = "interval"
        camera.screenshot_config["interval_sec"] = 10
        camera._last_screenshot_ts = 1000.0

        assert camera._should_save_screenshot(1005.0) is False
        assert camera._should_save_screenshot(1011.0) is True

    def test_should_save_screenshot_disabled(self, camera):
        """测试截图禁用"""
        camera.screenshot_config["enabled"] = False

        assert camera._should_save_screenshot(1000.0) is False

    def test_get_frame_no_frame(self, camera):
        """测试获取帧（无帧）"""
        camera.frame = None

        frame = camera.get_frame()
        assert frame is None

    def test_get_frame_with_frame(self, camera):
        """测试获取帧（有帧）"""
        test_frame = np.zeros((480, 640, 3), dtype=np.uint8)
        camera.frame = test_frame

        frame = camera.get_frame()

        assert frame is not None
        assert frame.shape == test_frame.shape
        # 应该返回副本，不是原始帧
        assert frame is not test_frame

    def test_emit_log_with_callback(self, camera):
        """测试日志发送（有回调）"""
        callback = Mock()
        camera.signal_callback = callback

        camera._emit_log("info", "test.event", "测试消息", {"key": "value"})

        callback.assert_called_once()
        call_args = callback.call_args[0][0]
        assert call_args["type"] == "log"
        assert call_args["level"] == "info"
        assert call_args["event"] == "test.event"

    def test_emit_log_no_callback(self, camera):
        """测试日志发送（无回调）"""
        camera.signal_callback = None

        # 不应该抛出异常
        camera._emit_log("info", "test.event", "测试消息")

    def test_emit_status_with_callback(self, camera):
        """测试状态发送（有回调）"""
        callback = Mock()
        camera.signal_callback = callback

        camera._emit_status("info", "测试状态", {"connected": True})

        callback.assert_called_once()
        call_args = callback.call_args[0][0]
        assert call_args["type"] == "status"
        assert call_args["level"] == "info"

    def test_now_iso_format(self, camera):
        """测试时间戳格式"""
        from datetime import datetime
        ts = camera._now_iso()
        # 不抛出异常即为正确格式
        datetime.fromisoformat(ts)

    @pytest.mark.boundary
    def test_track_id_overflow(self, camera):
        """测试 Track ID 溢出"""
        camera._next_track_id = 2**31 - 1

        boxes = [(10, 10, 50, 50)]
        track_ids = camera._associate_tracks(boxes, 1000.0)

        assert len(track_ids) == 1

    @pytest.mark.boundary
    def test_empty_boxes(self, camera):
        """测试空检测框"""
        boxes = []
        track_ids = camera._associate_tracks(boxes, 1000.0)

        assert len(track_ids) == 0

    @pytest.mark.boundary
    def test_many_detections(self, camera):
        """测试大量检测"""
        boxes = [(i * 10, i * 10, i * 10 + 40, i * 10 + 40) for i in range(100)]
        track_ids = camera._associate_tracks(boxes, 1000.0)

        assert len(track_ids) == 100
        assert len(camera._tracks) == 100

    @pytest.mark.boundary
    def test_iou_zero_area_box(self):
        """测试零面积检测框"""
        box1 = (5, 5, 5, 5)  # 零面积
        box2 = (0, 0, 10, 10)

        iou = CameraManager._iou(box1, box2)
        assert iou == 0.0

    def test_camera_with_db_manager(self, screenshot_config):
        """测试带数据库管理器的摄像头"""
        mock_db = Mock()
        camera = CameraManager(
            camera_id=1,
            source=1,
            db_manager=mock_db,
            screenshot_config=screenshot_config,
        )

        assert camera.db_manager is mock_db

    def test_camera_with_redis_stats(self, screenshot_config):
        """测试带 Redis 统计的摄像头"""
        mock_redis = Mock()
        camera = CameraManager(
            camera_id=1,
            source=1,
            redis_stats=mock_redis,
            screenshot_config=screenshot_config,
        )

        assert camera.redis_stats is mock_redis

    def test_camera_stop_not_running(self, camera):
        """测试停止未运行的摄像头"""
        camera.running = False
        camera.cap = None

        # 不应该抛出异常
        camera.stop()

    def test_camera_start_sets_running(self, camera):
        """测试启动设置运行状态"""
        with patch.object(camera, '_load_model'):
            with patch('threading.Thread') as mock_thread:
                mock_t = Mock()
                mock_thread.return_value = mock_t

                camera.start()

                assert camera.running is True
                mock_t.start.assert_called_once()

                # 清理
                camera.running = False
