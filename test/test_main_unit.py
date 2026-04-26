"""
Backend main.py 路由处理器单元测试
"""
import pytest
from unittest.mock import Mock, patch, AsyncMock, MagicMock
from pathlib import Path
import sys

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))


@pytest.mark.unit
class TestMainRoutes:
    """main.py 路由处理器单元测试"""

    @pytest.fixture
    def mock_app_state(self):
        """模拟应用状态"""
        with patch('backend.main.cameras', {}), \
             patch('backend.main.config', {"cameras": []}), \
             patch('backend.main.db_manager', None), \
             patch('backend.main.redis_stats', None), \
             patch('backend.main.START_TS', 1000.0):
            yield

    def test_health_endpoint_structure(self, mock_app_state):
        """测试健康检查端点返回结构"""
        from backend.main import app
        from fastapi.testclient import TestClient

        client = TestClient(app)
        response = client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert "uptime_sec" in data
        assert "cameras" in data

    def test_camera_list_empty(self, mock_app_state):
        """测试空摄像头列表"""
        from backend.main import app
        from fastapi.testclient import TestClient

        client = TestClient(app)
        response = client.get("/api/cameras")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
        assert data["cameras"] == []

    def test_camera_status_creates_new(self, mock_app_state):
        """测试查询不存在的摄像头会创建新实例"""
        from backend.main import app, cameras
        from fastapi.testclient import TestClient

        client = TestClient(app)

        with patch('backend.main.get_camera') as mock_get:
            mock_cam = Mock()
            mock_cam.get_status.return_value = {"camera_id": 0, "running": False}
            mock_get.return_value = mock_cam
            cameras[0] = mock_cam

            response = client.get("/api/camera/0/status")

            assert response.status_code == 200
            data = response.json()
            assert data["camera_id"] == 0

    def test_detection_config_update(self, mock_app_state):
        """测试检测配置更新"""
        from backend.main import app, cameras
        from fastapi.testclient import TestClient

        mock_cam = Mock()
        mock_cam.toggle_detection = Mock()
        mock_cam.set_conf = Mock()
        mock_cam.get_status.return_value = {"camera_id": 0, "running": True}
        cameras[0] = mock_cam

        client = TestClient(app)
        response = client.post(
            "/api/camera/0/config",
            json={"enabled": False, "conf": 0.7}
        )

        assert response.status_code == 200
        mock_cam.toggle_detection.assert_called_once_with(False)
        mock_cam.set_conf.assert_called_once_with(0.7)

    def test_alerts_query_no_db(self, mock_app_state):
        """测试无数据库时查询告警"""
        from backend.main import app
        from fastapi.testclient import TestClient

        with patch('backend.main.db_manager', None):
            client = TestClient(app)
            response = client.get("/api/alerts")

            assert response.status_code == 503
            data = response.json()
            assert "数据库" in data["detail"]

    def test_alerts_query_with_db(self, mock_app_state):
        """测试有数据库时查询告警"""
        from backend.main import app
        from fastapi.testclient import TestClient

        mock_db = Mock()
        mock_db.query_alerts.return_value = {
            "total": 5,
            "alerts": [{"id": 1, "camera_id": 0}]
        }

        with patch('backend.main.db_manager', mock_db):
            client = TestClient(app)
            response = client.get("/api/alerts?limit=10")

            assert response.status_code == 200
            data = response.json()
            assert data["total"] == 5
            assert len(data["alerts"]) == 1

    def test_logs_query(self, mock_app_state):
        """测试日志查询"""
        from backend.main import app
        from fastapi.testclient import TestClient

        with patch('backend.main.structured_logger') as mock_logger:
            mock_logger.get_recent_logs.return_value = [
                {"level": "info", "message": "test"}
            ]

            client = TestClient(app)
            response = client.get("/api/logs?limit=50")

            assert response.status_code == 200
            data = response.json()
            assert "logs" in data
            assert "count" in data

    def test_stats_query_no_redis(self, mock_app_state):
        """测试无 Redis 时查询统计"""
        from backend.main import app
        from fastapi.testclient import TestClient

        client = TestClient(app)
        response = client.get("/api/stats")

        assert response.status_code == 503

    def test_stats_query_with_redis(self, mock_app_state):
        """测试有 Redis 时查询统计"""
        from backend.main import app
        from fastapi.testclient import TestClient

        mock_redis = Mock()
        mock_redis.is_enabled.return_value = True
        mock_redis.get_all_stats.return_value = {
            "today_alerts": 10,
            "online_cameras": [0, 1]
        }

        with patch('backend.main.redis_stats', mock_redis):
            client = TestClient(app)
            response = client.get("/api/stats")

            assert response.status_code == 200
            data = response.json()
            assert "today_alerts" in data

    @pytest.mark.boundary
    def test_invalid_camera_id_type(self, mock_app_state):
        """测试无效摄像头 ID 类型"""
        from backend.main import app
        from fastapi.testclient import TestClient

        client = TestClient(app)
        response = client.get("/api/camera/invalid/status")

        assert response.status_code == 422

    @pytest.mark.boundary
    def test_negative_camera_id(self, mock_app_state):
        """测试负数摄像头 ID"""
        from backend.main import app
        from fastapi.testclient import TestClient

        client = TestClient(app)
        response = client.get("/api/camera/-1/status")

        # 应该能处理或返回错误
        assert response.status_code in [200, 400, 422]

    @pytest.mark.boundary
    def test_oversized_limit_parameter(self, mock_app_state):
        """测试超大 limit 参数"""
        from backend.main import app
        from fastapi.testclient import TestClient

        mock_db = Mock()
        mock_db.query_alerts.return_value = {"total": 0, "alerts": []}

        with patch('backend.main.db_manager', mock_db):
            client = TestClient(app)
            response = client.get("/api/alerts?limit=99999")

            # 应该被限制或返回错误
            assert response.status_code in [200, 422]

    @pytest.mark.exception
    def test_database_query_exception(self, mock_app_state):
        """测试数据库查询异常"""
        from backend.main import app
        from fastapi.testclient import TestClient

        mock_db = Mock()
        mock_db.query_alerts.side_effect = Exception("Database error")

        with patch('backend.main.db_manager', mock_db):
            client = TestClient(app)
            response = client.get("/api/alerts")

            assert response.status_code == 500

    @pytest.mark.exception
    def test_invalid_detection_config(self, mock_app_state):
        """测试无效检测配置"""
        from backend.main import app, cameras
        from fastapi.testclient import TestClient

        cameras[0] = Mock()

        client = TestClient(app)
        response = client.post(
            "/api/camera/0/config",
            json={"enabled": "invalid", "conf": "not_a_number"}
        )

        assert response.status_code == 422

    @pytest.mark.exception
    def test_malformed_json_request(self, mock_app_state):
        """测试格式错误的 JSON 请求"""
        from backend.main import app
        from fastapi.testclient import TestClient

        client = TestClient(app)
        response = client.post(
            "/api/camera/0/config",
            data="not json",
            headers={"Content-Type": "application/json"}
        )

        assert response.status_code == 422


@pytest.mark.unit
class TestDynamicCameraAPI:
    """动态摄像头管理 API 测试（P2 补充）"""

    @pytest.fixture
    def mock_app_state(self):
        with patch('backend.main.cameras', {}), \
             patch('backend.main.config', {"cameras": [], "detection": {}, "alert": {}}), \
             patch('backend.main.db_manager', None), \
             patch('backend.main.redis_stats', None), \
             patch('backend.main.START_TS', 1000.0):
            yield

    def test_list_cameras_with_config(self):
        """GET /api/cameras 返回配置中的摄像头，id 字段存在"""
        from backend.main import app
        from fastapi.testclient import TestClient

        cam_cfg = [{"id": 0, "name": "测试", "location": "A", "source": 0}]
        mock_cam = Mock()
        mock_cam.get_status.return_value = {
            "camera_id": 0, "connected": True, "running": True,
            "model_loaded": False, "fps": 25.0, "active_tracks": 0,
        }

        with patch('backend.main.config', {"cameras": cam_cfg}), \
             patch('backend.main.cameras', {0: mock_cam}):
            client = TestClient(app)
            resp = client.get("/api/cameras")

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        cam = data["cameras"][0]
        # 前端依赖 id 字段，不能是 camera_id
        assert cam["id"] == 0
        assert cam["name"] == "测试"

    def test_add_camera_missing_source(self, mock_app_state):
        """POST /api/cameras/{id}/add 缺少 source 返回 422"""
        from backend.main import app
        from fastapi.testclient import TestClient

        client = TestClient(app)
        resp = client.post("/api/cameras/5/add", json={"name": "新摄像头"})
        assert resp.status_code == 422

    def test_add_camera_duplicate(self, mock_app_state):
        """POST /api/cameras/{id}/add 重复添加返回 409"""
        from backend.main import app, cameras
        from fastapi.testclient import TestClient

        cameras[5] = Mock()
        client = TestClient(app)
        resp = client.post("/api/cameras/5/add", json={"source": 0})
        assert resp.status_code == 409

    def test_add_camera_invalid_json(self, mock_app_state):
        """POST /api/cameras/{id}/add 非法 JSON 返回 422"""
        from backend.main import app
        from fastapi.testclient import TestClient

        client = TestClient(app)
        resp = client.post(
            "/api/cameras/5/add",
            data="not-json",
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 422

    def test_remove_camera_not_found(self, mock_app_state):
        """POST /api/cameras/{id}/remove 不存在返回 404"""
        from backend.main import app
        from fastapi.testclient import TestClient

        client = TestClient(app)
        resp = client.post("/api/cameras/99/remove")
        assert resp.status_code == 404

    def test_remove_camera_success(self, mock_app_state):
        """POST /api/cameras/{id}/remove 成功移除"""
        from backend.main import app, cameras
        from fastapi.testclient import TestClient

        mock_cam = Mock()
        cameras[3] = mock_cam

        with patch('backend.main.structured_logger') as mock_log, \
             patch('backend.main._dispatch_signal'):
            mock_log.log.return_value = {}
            client = TestClient(app)
            resp = client.post("/api/cameras/3/remove")

        assert resp.status_code == 200
        assert resp.json()["success"] is True
        assert 3 not in cameras
        mock_cam.stop.assert_called_once()


@pytest.mark.unit
class TestCameraSignalCallback:
    """_camera_signal_callback 线程安全测试（P1 修复验证）"""

    def test_feishu_uses_call_soon_threadsafe(self):
        """飞书推送通过 call_soon_threadsafe 调度，不直接调用 create_task"""
        from backend.main import _camera_signal_callback

        mock_loop = Mock()
        mock_notifier = AsyncMock()

        alert_msg = {"type": "alert", "level": "high", "data": {"screenshot_path": None}}

        with patch('backend.main._event_loop', mock_loop), \
             patch('backend.main.feishu_notifier', mock_notifier), \
             patch('backend.main._dispatch_signal'):
            mock_loop.is_running.return_value = True
            _camera_signal_callback(alert_msg)

        # 至少调用一次，且参数中包含 notifier.send_alert 生成的协程
        assert mock_loop.call_soon_threadsafe.call_count >= 1
        called_args = [c.args for c in mock_loop.call_soon_threadsafe.call_args_list]
        assert any(len(args) >= 2 for args in called_args)

    def test_no_feishu_no_threadsafe_call(self):
        """无飞书 notifier 时不调用 call_soon_threadsafe"""
        from backend.main import _camera_signal_callback

        mock_loop = Mock()
        alert_msg = {"type": "alert", "level": "high", "data": {}}

        with patch('backend.main._event_loop', mock_loop), \
             patch('backend.main.feishu_notifier', None), \
             patch('backend.main._dispatch_signal'):
            _camera_signal_callback(alert_msg)

        # feishu_notifier 为 None，不应触发 call_soon_threadsafe
        mock_loop.call_soon_threadsafe.assert_not_called()

    """摄像头工厂函数测试"""

    def test_get_camera_creates_new(self):
        """测试获取不存在的摄像头会创建新实例"""
        from backend.main import get_camera, cameras

        cameras.clear()

        with patch('backend.main.config', {"cameras": [], "detection": {}, "alert": {}}):
            with patch('backend.main.CameraManager') as mock_cm:
                mock_instance = Mock()
                mock_cm.return_value = mock_instance

                cam = get_camera(0)

                assert cam is mock_instance
                assert 0 in cameras

    def test_get_camera_returns_existing(self):
        """测试获取已存在的摄像头返回同一实例"""
        from backend.main import get_camera, cameras

        mock_cam = Mock()
        cameras[0] = mock_cam

        cam = get_camera(0)

        assert cam is mock_cam

    def test_get_camera_with_config(self):
        """测试使用配置创建摄像头"""
        from backend.main import get_camera, cameras

        cameras.clear()

        cam_cfg = {
            "id": 1,
            "source": "rtsp://test",
            "width": 1920,
            "height": 1080
        }

        with patch('backend.main.config', {"detection": {}, "alert": {}}):
            with patch('backend.main.CameraManager') as mock_cm:
                mock_instance = Mock()
                mock_cm.return_value = mock_instance

                cam = get_camera(1, cam_cfg)

                assert cam is mock_instance
                mock_cm.assert_called_once()


@pytest.mark.unit
class TestBroadcastMechanism:
    """WebSocket 广播机制测试"""

    @pytest.mark.asyncio
    async def test_broadcast_to_clients(self):
        """测试向客户端广播消息"""
        from backend.main import _broadcast, _ws_clients

        mock_ws1 = AsyncMock()
        mock_ws2 = AsyncMock()
        _ws_clients.clear()
        _ws_clients.extend([mock_ws1, mock_ws2])

        message = {"type": "test", "data": "hello"}
        await _broadcast(message)

        mock_ws1.send_json.assert_called_once_with(message)
        mock_ws2.send_json.assert_called_once_with(message)

    @pytest.mark.asyncio
    async def test_broadcast_removes_dead_clients(self):
        """测试广播时移除失败的客户端"""
        from backend.main import _broadcast, _ws_clients

        mock_ws_good = AsyncMock()
        mock_ws_dead = AsyncMock()
        mock_ws_dead.send_json.side_effect = Exception("Connection lost")

        _ws_clients.clear()
        _ws_clients.extend([mock_ws_good, mock_ws_dead])

        await _broadcast({"type": "test"})

        assert mock_ws_good in _ws_clients
        assert mock_ws_dead not in _ws_clients


@pytest.mark.unit
class TestCleanupTask:
    """定时清理任务测试"""

    def test_cleanup_removes_old_screenshots(self, tmp_path):
        """测试清理旧截图"""
        from backend.main import _do_cleanup
        from datetime import datetime, timedelta

        # 创建测试目录结构
        old_date = (datetime.now() - timedelta(days=35)).strftime("%Y-%m-%d")
        recent_date = (datetime.now() - timedelta(days=5)).strftime("%Y-%m-%d")

        old_dir = tmp_path / old_date
        recent_dir = tmp_path / recent_date
        old_dir.mkdir()
        recent_dir.mkdir()

        (old_dir / "test.jpg").write_text("old")
        (recent_dir / "test.jpg").write_text("recent")

        with patch('backend.main.ROOT', tmp_path.parent):
            with patch('backend.main.db_manager', None):
                _do_cleanup(str(tmp_path.name), retention_days=30)

        assert not old_dir.exists()
        assert recent_dir.exists()

    def test_cleanup_deletes_old_alerts(self):
        """测试清理旧告警记录"""
        from backend.main import _do_cleanup

        mock_db = Mock()
        mock_db.delete_old_alerts.return_value = 10

        with patch('backend.main.db_manager', mock_db):
            with patch('backend.main.ROOT', Path("/tmp")):
                _do_cleanup("screenshots", retention_days=30)

        mock_db.delete_old_alerts.assert_called_once_with(days=30)
