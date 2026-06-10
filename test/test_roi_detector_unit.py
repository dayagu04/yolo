"""roi_detector.py 单元测试"""
import pytest
import numpy as np
from unittest.mock import MagicMock
from backend.roi_detector import ROIDetector


@pytest.fixture
def db_mock():
    db = MagicMock()
    db.get_rois.return_value = []
    return db


@pytest.fixture
def detector(db_mock):
    return ROIDetector(db_manager=db_mock)


# ── 点在多边形内判断 ──

class TestPointInPolygon:
    def test_point_inside_square(self):
        polygon = np.array([[0, 0], [100, 0], [100, 100], [0, 100]])
        assert ROIDetector._point_in_polygon(50, 50, polygon) is True

    def test_point_outside_square(self):
        polygon = np.array([[0, 0], [100, 0], [100, 100], [0, 100]])
        assert ROIDetector._point_in_polygon(150, 50, polygon) is False

    def test_point_on_edge(self):
        polygon = np.array([[0, 0], [100, 0], [100, 100], [0, 100]])
        # 边界上的点行为取决于实现，但不应崩溃
        result = ROIDetector._point_in_polygon(0, 50, polygon)
        assert isinstance(result, bool)

    def test_triangle(self):
        polygon = np.array([[50, 0], [100, 100], [0, 100]])
        assert ROIDetector._point_in_polygon(50, 50, polygon) is True
        assert ROIDetector._point_in_polygon(10, 10, polygon) is False


# ── 入侵检测 ──

class TestIntrusionDetection:
    def test_no_rois(self, detector, db_mock):
        db_mock.get_rois.return_value = []
        alerts = detector.check_intrusion(0, [(10, 10, 50, 50)], [1])
        assert alerts == []

    def test_intrusion_detected(self, detector, db_mock):
        db_mock.get_rois.return_value = [{
            "id": 1, "camera_id": 0, "name": "禁区",
            "roi_type": "intrusion", "enabled": True,
            "polygon": [[0, 0], [100, 0], [100, 100], [0, 100]],
            "min_persons": 1, "alert_level": "high",
        }]
        detector._last_load_ts = 0  # 强制重新加载
        detector._reload_rois()

        # bbox 底部中心 (30, 80) 在多边形内
        alerts = detector.check_intrusion(0, [(10, 10, 50, 80)], [1])
        assert len(alerts) == 1
        assert alerts[0]["roi_type"] == "intrusion"
        assert alerts[0]["person_count"] == 1

    def test_intrusion_not_detected_outside(self, detector, db_mock):
        db_mock.get_rois.return_value = [{
            "id": 1, "camera_id": 0, "name": "禁区",
            "roi_type": "intrusion", "enabled": True,
            "polygon": [[0, 0], [100, 0], [100, 100], [0, 100]],
            "min_persons": 1, "alert_level": "high",
        }]
        detector._last_load_ts = 0
        detector._reload_rois()

        # bbox 底部中心 (200, 200) 在多边形外
        alerts = detector.check_intrusion(0, [(180, 180, 220, 200)], [1])
        assert len(alerts) == 0

    def test_min_persons_threshold(self, detector, db_mock):
        db_mock.get_rois.return_value = [{
            "id": 1, "camera_id": 0, "name": "聚集区",
            "roi_type": "intrusion", "enabled": True,
            "polygon": [[0, 0], [200, 0], [200, 200], [0, 200]],
            "min_persons": 3, "alert_level": "high",
        }]
        detector._last_load_ts = 0
        detector._reload_rois()

        # 只有 2 人在区域内，阈值是 3
        alerts = detector.check_intrusion(0, [(10, 10, 50, 50), (60, 10, 100, 50)], [1, 2])
        assert len(alerts) == 0


# ── 聚集检测 ──

class TestGatheringDetection:
    def test_gathering_detected(self, detector, db_mock):
        db_mock.get_rois.return_value = [{
            "id": 1, "camera_id": 0, "name": "广场",
            "roi_type": "gathering", "enabled": True,
            "polygon": [[0, 0], [200, 0], [200, 200], [0, 200]],
            "min_persons": 3, "alert_level": "medium",
        }]
        detector._last_load_ts = 0
        detector._reload_rois()

        bboxes = [(10, 10, 50, 50), (60, 10, 100, 50), (110, 10, 150, 50)]
        alerts = detector.check_gathering(0, bboxes, [1, 2, 3])
        assert len(alerts) == 1
        assert alerts[0]["person_count"] == 3


# ── 清理过期跟踪 ──

class TestCleanup:
    def test_cleanup_stale_tracks(self, detector):
        import time
        now = time.time()
        detector._person_tracks = {
            "0_1": {"positions": [(1, 2)], "timestamps": [now - 400], "in_roi_since": None},
            "0_2": {"positions": [(3, 4)], "timestamps": [now - 100], "in_roi_since": None},
        }
        detector.cleanup_stale_tracks(max_age_sec=300)
        assert "0_1" not in detector._person_tracks
        assert "0_2" in detector._person_tracks


# ── 全部检测 ──

class TestCheckAll:
    def test_check_all_no_rois(self, detector, db_mock):
        db_mock.get_rois.return_value = []
        alerts = detector.check_all(0, [(10, 10, 50, 50)], [1])
        assert alerts == []

    def test_check_all_triggers_stale_cleanup(self, detector, db_mock):
        """check_all 在跟踪记录过多时触发清理，防止 _person_tracks 无限增长（回归测试）"""
        import time
        db_mock.get_rois.return_value = []
        now = time.time()
        # 注入 101 条全部过期的跟踪记录（超过 100 阈值）
        detector._person_tracks = {
            f"0_{i}": {"positions": [(1, 2)], "timestamps": [now - 400],
                       "in_roi_since": None}
            for i in range(101)
        }
        detector.check_all(0, [(10, 10, 50, 50)], [1])
        # 过期记录应被清理
        assert len(detector._person_tracks) == 0


# ── 徘徊重复告警回归测试 ──

class TestLoiteringReAlert:
    """验证徘徊告警达到阈值后只触发一次，不再每帧重复（bug 回归）"""

    @pytest.fixture
    def loiter_detector(self, db_mock):
        db_mock.get_rois.return_value = [{
            "id": 1, "camera_id": 0, "name": "徘徊区",
            "roi_type": "loitering", "enabled": True,
            "polygon": [[0, 0], [100, 0], [100, 100], [0, 100]],
            "min_persons": 1, "min_duration_sec": 5, "alert_level": "medium",
        }]
        det = ROIDetector(db_manager=db_mock)
        det._last_load_ts = 0
        det._reload_rois()
        return det

    def test_loitering_alerts_once_then_suppressed(self, loiter_detector):
        """持续停留时只在跨过阈值的那一帧告警一次"""
        import time
        bbox = (10, 10, 50, 80)  # 底部中心 (30, 80) 在多边形内
        track_ids = [1]

        # 第 1 帧：进入区域，记录 in_roi_since，未达阈值
        loiter_detector.check_loitering(0, [bbox], track_ids)
        track = loiter_detector._person_tracks["0_1"]
        # 手动回拨进入时间，模拟已停留超过 min_duration_sec
        track["in_roi_since"] = time.time() - 10

        # 第 2 帧：达到阈值，应触发一次告警
        alerts1 = loiter_detector.check_loitering(0, [bbox], track_ids)
        assert len(alerts1) == 1
        assert alerts1[0]["roi_type"] == "loitering"

        # 第 3、4 帧：仍在区域内，不应再次告警
        alerts2 = loiter_detector.check_loitering(0, [bbox], track_ids)
        alerts3 = loiter_detector.check_loitering(0, [bbox], track_ids)
        assert alerts2 == []
        assert alerts3 == []

    def test_loitering_realerts_after_leaving_and_returning(self, loiter_detector):
        """离开区域后重新进入并再次停留，应能再次告警"""
        import time
        inside = (10, 10, 50, 80)
        outside = (200, 200, 250, 280)  # 多边形外
        track_ids = [1]

        # 进入并触发一次
        loiter_detector.check_loitering(0, [inside], track_ids)
        loiter_detector._person_tracks["0_1"]["in_roi_since"] = time.time() - 10
        assert len(loiter_detector.check_loitering(0, [inside], track_ids)) == 1

        # 离开区域，重置告警标志
        loiter_detector.check_loitering(0, [outside], track_ids)
        track = loiter_detector._person_tracks["0_1"]
        assert track["in_roi_since"] is None
        assert track["alerted_loitering"] is False

        # 再次进入并停留，应能再次告警
        loiter_detector.check_loitering(0, [inside], track_ids)
        loiter_detector._person_tracks["0_1"]["in_roi_since"] = time.time() - 10
        assert len(loiter_detector.check_loitering(0, [inside], track_ids)) == 1
