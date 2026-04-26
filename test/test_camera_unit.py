"""
Camera 模块单元测试（对应 PersonTracker + ScreenshotManager 拆分后的接口）
"""
import pytest
import numpy as np
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path
import sys

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from backend.camera import CameraManager
from backend.tracker import PersonTracker
from backend.screenshot import ScreenshotManager


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

    def test_alert_cooldown_proxy(self, camera):
        """测试告警冷却时间属性代理到 tracker"""
        camera._alert_cooldown_sec = 30.0
        assert camera.tracker.alert_cooldown_sec == 30.0
        assert camera._alert_cooldown_sec == 30.0

    def test_track_ttl_proxy(self, camera):
        """测试轨迹 TTL 属性代理到 tracker"""
        camera._track_ttl_sec = 10.0
        assert camera.tracker.track_ttl_sec == 10.0
        assert camera._track_ttl_sec == 10.0


@pytest.mark.unit
class TestPersonTracker:
    """PersonTracker 单元测试"""

    @pytest.fixture
    def tracker(self):
        return PersonTracker(track_ttl_sec=5.0, alert_cooldown_sec=3.0)

    def test_iou_calculation(self, tracker):
        """测试 IoU 计算"""
        box1 = (0, 0, 10, 10)
        box2 = (5, 5, 15, 15)

        iou = PersonTracker._iou(box1, box2)

        # 交集面积 = 5*5 = 25，并集面积 = 100 + 100 - 25 = 175
        assert 0.14 < iou < 0.15

    def test_iou_no_overlap(self, tracker):
        """测试无重叠的 IoU"""
        box1 = (0, 0, 10, 10)
        box2 = (20, 20, 30, 30)

        iou = PersonTracker._iou(box1, box2)
        assert iou == 0.0

    def test_iou_complete_overlap(self, tracker):
        """测试完全重叠的 IoU"""
        box1 = (0, 0, 10, 10)
        box2 = (0, 0, 10, 10)

        iou = PersonTracker._iou(box1, box2)
        assert iou == 1.0

    def test_iou_zero_area_box(self):
        """测试零面积检测框"""
        box1 = (5, 5, 5, 5)  # 零面积
        box2 = (0, 0, 10, 10)

        iou = PersonTracker._iou(box1, box2)
        assert iou == 0.0

    def test_associate_tracks_new_detection(self, tracker):
        """测试新检测的 Track 关联"""
        boxes = [(10, 10, 50, 50)]
        now_ts = 1000.0

        track_ids = tracker.associate(boxes, now_ts)

        assert len(track_ids) == 1
        assert len(tracker._tracks) == 1

    def test_associate_tracks_existing_detection(self, tracker):
        """测试已存在检测的 Track 关联"""
        boxes1 = [(10, 10, 50, 50)]
        track_ids1 = tracker.associate(boxes1, 1000.0)

        # 位置略有变化
        boxes2 = [(12, 12, 52, 52)]
        track_ids2 = tracker.associate(boxes2, 1001.0)

        # 应该关联到同一个 Track
        assert track_ids1[0] == track_ids2[0]
        assert len(tracker._tracks) == 1

    def test_associate_tracks_expired(self, tracker):
        """测试过期 Track 清理"""
        tracker.track_ttl_sec = 5

        boxes1 = [(10, 10, 50, 50)]
        tracker.associate(boxes1, 1000.0)

        # 6秒后再次检测（超过 TTL）
        boxes2 = [(10, 10, 50, 50)]
        tracker.associate(boxes2, 1006.0)

        # 旧 Track 应该被清理，创建新 Track
        assert len(tracker._tracks) == 1

    def test_empty_boxes(self, tracker):
        """测试空检测框"""
        track_ids = tracker.associate([], 1000.0)
        assert len(track_ids) == 0

    def test_many_detections(self, tracker):
        """测试大量检测"""
        boxes = [(i * 100, i * 100, i * 100 + 40, i * 100 + 40) for i in range(50)]
        track_ids = tracker.associate(boxes, 1000.0)

        assert len(track_ids) == 50
        assert len(tracker._tracks) == 50

    def test_track_id_overflow(self, tracker):
        """测试 Track ID 溢出"""
        tracker._next_track_id = 2**31 - 1

        boxes = [(10, 10, 50, 50)]
        track_ids = tracker.associate(boxes, 1000.0)

        assert len(track_ids) == 1

    def test_get_pending_tracks_cooldown(self, tracker):
        """测试告警冷却期内不返回待告警轨迹"""
        boxes = [(10, 10, 50, 50)]
        active_ids = tracker.associate(boxes, 1000.0)
        # 第一次告警
        pending = tracker.get_pending_tracks(active_ids, 1000.0)
        tracker.mark_alerted(pending, 1000.0)

        # 新轨迹，但在冷却期内
        boxes2 = [(200, 200, 240, 240)]
        active_ids2 = tracker.associate(boxes2, 1001.0)
        pending2 = tracker.get_pending_tracks(active_ids2, 1001.0)

        assert pending2 == []

    def test_active_count(self, tracker):
        """测试活跃轨迹计数"""
        assert tracker.active_count == 0

        boxes = [(10, 10, 50, 50), (200, 200, 240, 240)]
        tracker.associate(boxes, 1000.0)

        assert tracker.active_count == 2


@pytest.mark.unit
class TestScreenshotManager:
    """ScreenshotManager 单元测试"""

    @pytest.fixture
    def mgr_first_only(self, tmp_path):
        config = {
            "enabled": True,
            "save_mode": "first_only",
            "quality": 75,
            "save_dir": "screenshots",
        }
        return ScreenshotManager(camera_id=0, config=config, root_path=tmp_path)

    @pytest.fixture
    def mgr_all(self, tmp_path):
        config = {
            "enabled": True,
            "save_mode": "all",
            "quality": 75,
            "save_dir": "screenshots",
        }
        return ScreenshotManager(camera_id=0, config=config, root_path=tmp_path)

    @pytest.fixture
    def mgr_interval(self, tmp_path):
        config = {
            "enabled": True,
            "save_mode": "interval",
            "interval_sec": 10,
            "quality": 75,
            "save_dir": "screenshots",
        }
        return ScreenshotManager(camera_id=0, config=config, root_path=tmp_path)

    @pytest.fixture
    def mgr_disabled(self, tmp_path):
        config = {
            "enabled": False,
            "save_mode": "all",
            "save_dir": "screenshots",
        }
        return ScreenshotManager(camera_id=0, config=config, root_path=tmp_path)

    def test_should_save_first_only(self, mgr_first_only):
        """测试首次截图模式"""
        assert mgr_first_only.should_save(1000.0, alert_total=0) is True
        assert mgr_first_only.should_save(1001.0, alert_total=1) is False

    def test_should_save_all(self, mgr_all):
        """测试全部截图模式"""
        assert mgr_all.should_save(1000.0, alert_total=0) is True
        assert mgr_all.should_save(1001.0, alert_total=5) is True

    def test_should_save_interval(self, mgr_interval):
        """测试间隔截图模式"""
        mgr_interval._last_ts = 1000.0
        assert mgr_interval.should_save(1005.0, alert_total=0) is False
        assert mgr_interval.should_save(1011.0, alert_total=0) is True

    def test_should_save_disabled(self, mgr_disabled):
        """测试截图禁用"""
        assert mgr_disabled.should_save(1000.0, alert_total=0) is False

    @patch('cv2.imwrite')
    def test_save_screenshot(self, mock_imwrite, mgr_all):
        """测试保存截图返回相对路径"""
        mock_imwrite.return_value = True
        frame = np.zeros((480, 640, 3), dtype=np.uint8)

        path = mgr_all.save(frame, 1000.0)

        assert path is not None
        assert ".jpg" in path
        mock_imwrite.assert_called_once()

    @patch('cv2.imwrite', side_effect=OSError("磁盘满"))
    def test_save_screenshot_failure(self, mock_imwrite, mgr_all):
        """测试保存失败时返回 None"""
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        path = mgr_all.save(frame, 1000.0)
        assert path is None
