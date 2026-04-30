"""补充测试：schemas、metrics、model_manager、capture_process"""
import pytest
import time
from unittest.mock import MagicMock, patch, PropertyMock


# ── schemas.py 测试 ──

class TestSchemas:
    def test_alert_message(self):
        from backend.schemas import AlertMessage
        msg = AlertMessage(timestamp="2024-01-01T00:00:00", message="test", camera_id=0)
        assert msg.type == "alert"
        assert msg.level == "high"

    def test_status_message(self):
        from backend.schemas import StatusMessage
        msg = StatusMessage(timestamp="2024-01-01T00:00:00", message="ok", camera_id=0)
        assert msg.type == "status"
        assert msg.level == "info"

    def test_log_message(self):
        from backend.schemas import LogMessage
        msg = LogMessage(timestamp="2024-01-01T00:00:00", message="log", event="test.event")
        assert msg.type == "log"
        assert msg.camera_id is None

    def test_login_request(self):
        from backend.schemas import LoginRequest
        req = LoginRequest(username="admin", password="pass")
        assert req.username == "admin"

    def test_login_request_validation(self):
        from backend.schemas import LoginRequest
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            LoginRequest(username="", password="pass")

    def test_token_response(self):
        from backend.schemas import TokenResponse
        resp = TokenResponse(access_token="tok", expires_in=3600, role="admin")
        assert resp.token_type == "bearer"
        assert resp.refresh_token == ""

    def test_user_info(self):
        from backend.schemas import UserInfo
        info = UserInfo(username="admin", role="admin")
        assert info.username == "admin"

    def test_camera_status(self):
        from backend.schemas import CameraStatus
        cs = CameraStatus(camera_id=0, running=True, connected=True,
                          model_loaded=True, detection_enabled=True, conf_threshold=0.5)
        assert cs.fps == 0.0

    def test_detection_config(self):
        from backend.schemas import DetectionConfig
        dc = DetectionConfig(enabled=True, conf=0.6)
        assert dc.enabled is True

    def test_health_response(self):
        from backend.schemas import HealthResponse
        hr = HealthResponse(status="ok", uptime_sec=100.0, ws_clients=2,
                            camera_count=1, cameras=[])
        assert hr.status == "ok"


# ── metrics.py 测试 ──

class TestMetrics:
    def test_collect_metrics_basic(self):
        from backend.metrics import collect_metrics
        cam = MagicMock()
        cam._fps = 25.0
        cam.connected = True
        cam.tracker = MagicMock()
        cam.tracker.active_count = 3
        cam._alert_total = 10
        cam._reconnect_attempts = 0

        result = collect_metrics({0: cam}, start_ts=time.time() - 100, ws_clients=5)
        assert "safecam_camera_fps" in result
        assert "safecam_ws_clients 5" in result
        assert "safecam_uptime_seconds" in result

    def test_collect_metrics_no_cameras(self):
        from backend.metrics import collect_metrics
        result = collect_metrics({}, start_ts=time.time())
        assert "safecam_ws_clients 0" in result

    @patch("backend.metrics.psutil")
    def test_collect_metrics_psutil_failure(self, mock_psutil):
        from backend.metrics import collect_metrics
        mock_psutil.cpu_percent.side_effect = RuntimeError("no cpu")
        result = collect_metrics({}, start_ts=time.time())
        # 应该不崩溃，CPU 指标缺失但其他正常
        assert "safecam_uptime_seconds" in result


# ── model_manager.py 测试 ──

class TestModelManager:
    def test_init(self):
        from backend.model_manager import ModelManager
        mm = ModelManager(models_dir="models")
        assert mm.loaded_count == 0

    def test_get_model_not_loaded(self):
        from backend.model_manager import ModelManager
        mm = ModelManager()
        assert mm.get_model("nonexistent") is None

    def test_unload_not_loaded(self):
        from backend.model_manager import ModelManager
        mm = ModelManager()
        assert mm.unload_model("nonexistent") is False

    def test_list_models_empty(self):
        from backend.model_manager import ModelManager
        mm = ModelManager()
        assert mm.list_models() == []

    def test_scan_available_empty_dir(self, tmp_path):
        from backend.model_manager import ModelManager
        mm = ModelManager(models_dir=str(tmp_path / "empty"))
        assert mm.scan_available() == []

    def test_scan_available_with_files(self, tmp_path):
        from backend.model_manager import ModelManager
        models_dir = tmp_path / "models"
        models_dir.mkdir()
        (models_dir / "test.pt").write_bytes(b"\x00" * 1024)
        mm = ModelManager(models_dir=str(models_dir))
        available = mm.scan_available()
        assert len(available) == 1
        assert available[0]["filename"] == "test.pt"

    @patch("backend.model_manager.YOLO")
    def test_load_model_success(self, mock_yolo_cls):
        from backend.model_manager import ModelManager
        mock_model = MagicMock()
        mock_model.names = {0: "person"}
        mock_yolo_cls.return_value = mock_model

        mm = ModelManager()
        result = mm.load_model("test", "models/test.pt")
        assert result is True
        assert mm.loaded_count == 1
        assert mm.get_model("test") is mock_model

    @patch("backend.model_manager.YOLO")
    def test_load_model_failure(self, mock_yolo_cls):
        from backend.model_manager import ModelManager
        mock_yolo_cls.side_effect = RuntimeError("model not found")

        mm = ModelManager()
        result = mm.load_model("bad", "nonexistent.pt")
        assert result is False
        assert mm.loaded_count == 0

    @patch("backend.model_manager.YOLO")
    def test_unload_model_success(self, mock_yolo_cls):
        from backend.model_manager import ModelManager
        mock_model = MagicMock()
        mock_model.names = {0: "person"}
        mock_yolo_cls.return_value = mock_model

        mm = ModelManager()
        mm.load_model("test", "models/test.pt")
        assert mm.unload_model("test") is True
        assert mm.loaded_count == 0


# ── capture_process.py 测试 ──

class TestCaptureProcess:
    def test_init(self):
        from backend.capture_process import CaptureProcess
        cp = CaptureProcess(camera_id=0, source=0, width=640, height=480)
        assert cp.camera_id == 0
        assert cp._frame_shape == (480, 640, 3)
        assert cp.width == 640

    def test_read_frame_no_shm(self):
        from backend.capture_process import CaptureProcess
        cp = CaptureProcess(camera_id=0, source=0)
        # 未启动时共享内存不存在
        frame = cp.read_frame()
        assert frame is None

    def test_stop_without_start(self):
        from backend.capture_process import CaptureProcess
        cp = CaptureProcess(camera_id=0, source=0)
        # 不应崩溃
        cp.stop()
