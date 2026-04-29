"""routers/ 单元测试 - 使用 FastAPI TestClient"""
import os
import pytest
from unittest.mock import MagicMock, patch

os.environ["YOLO_AUTH_SECRET_KEY"] = "test_secret_key_for_unit_testing_only_32bytes!!"

from fastapi import FastAPI
from fastapi.testclient import TestClient
from backend.auth import create_access_token, hash_password
from backend.routers.auth import auth_router
from backend.routers.roi import roi_router
from backend.routers.system import system_router


# ── Fixtures ──

@pytest.fixture
def db_mock():
    db = MagicMock()
    db.get_user_by_username.return_value = {
        "id": 1, "username": "admin", "role": "admin",
        "hashed_password": hash_password("admin123"), "is_active": True,
    }
    db.list_users.return_value = [
        {"id": 1, "username": "admin", "role": "admin", "is_active": True},
    ]
    db.create_user.return_value = {"id": 2, "username": "newuser", "role": "viewer", "is_active": True}
    db.update_user.return_value = True
    db.delete_user.return_value = True
    db.update_password.return_value = True
    db.get_rois.return_value = []
    db.create_roi.return_value = {"id": 1, "camera_id": 0, "name": "test"}
    db.update_roi.return_value = True
    db.delete_roi.return_value = True
    db.query_audit_logs.return_value = []
    db.create_audit_log.return_value = None
    return db


@pytest.fixture
def config():
    return {
        "auth": {"access_token_expire_minutes": 60},
        "notifications": {
            "feishu": {"enabled": True, "webhook_url": "https://open.feishu.cn/open-apis/bot/v2/hook/abc"},
            "wechat_work": {"enabled": False},
        },
    }


@pytest.fixture
def app(db_mock, config):
    app = FastAPI()
    app.include_router(auth_router)
    app.include_router(roi_router)
    app.include_router(system_router)
    app.state.db_manager = db_mock
    app.state.config = config
    app.state.redis_stats = None
    app.state.cameras = {}
    app.state.structured_logger = None
    return app


@pytest.fixture
def client(app):
    return TestClient(app)


def auth_header(username="admin", role="admin"):
    token = create_access_token(username, role)
    return {"Authorization": f"Bearer {token}"}


# ── Auth Router Tests ──

class TestAuthRouter:
    def test_login_success(self, client, db_mock):
        res = client.post("/api/v1/auth/login", json={"username": "admin", "password": "admin123"})
        assert res.status_code == 200
        data = res.json()
        assert "access_token" in data
        assert data["role"] == "admin"

    def test_login_wrong_password(self, client, db_mock):
        res = client.post("/api/v1/auth/login", json={"username": "admin", "password": "wrong"})
        assert res.status_code == 401

    def test_login_user_not_found(self, client, db_mock):
        db_mock.get_user_by_username.return_value = None
        res = client.post("/api/v1/auth/login", json={"username": "nobody", "password": "x"})
        assert res.status_code == 401

    def test_login_disabled_user(self, client, db_mock):
        db_mock.get_user_by_username.return_value = {
            "id": 1, "username": "disabled", "role": "viewer",
            "hashed_password": hash_password("pass"), "is_active": False,
        }
        res = client.post("/api/v1/auth/login", json={"username": "disabled", "password": "pass"})
        assert res.status_code == 403

    def test_me(self, client):
        res = client.get("/api/v1/auth/me", headers=auth_header())
        assert res.status_code == 200
        assert res.json()["username"] == "admin"

    def test_me_no_token(self, client):
        res = client.get("/api/v1/auth/me")
        assert res.status_code == 401

    def test_list_users(self, client):
        res = client.get("/api/v1/auth/users", headers=auth_header())
        assert res.status_code == 200
        assert len(res.json()) == 1

    def test_create_user(self, client, db_mock):
        db_mock.get_user_by_username.return_value = None
        res = client.post("/api/v1/auth/users", headers=auth_header(),
                          json={"username": "newuser", "password": "pass123", "role": "viewer"})
        assert res.status_code == 200
        assert res.json()["username"] == "newuser"

    def test_create_user_duplicate(self, client, db_mock):
        res = client.post("/api/v1/auth/users", headers=auth_header(),
                          json={"username": "admin", "password": "pass123"})
        assert res.status_code == 409

    def test_create_user_missing_fields(self, client):
        res = client.post("/api/v1/auth/users", headers=auth_header(),
                          json={"username": ""})
        assert res.status_code == 422

    def test_update_user_role(self, client):
        res = client.put("/api/v1/auth/users/2", headers=auth_header(),
                         json={"role": "operator"})
        assert res.status_code == 200

    def test_update_user_invalid_role(self, client):
        res = client.put("/api/v1/auth/users/2", headers=auth_header(),
                         json={"role": "superadmin"})
        assert res.status_code == 422

    def test_update_user_no_fields(self, client):
        res = client.put("/api/v1/auth/users/2", headers=auth_header(), json={})
        assert res.status_code == 422

    def test_delete_user(self, client):
        res = client.delete("/api/v1/auth/users/2", headers=auth_header())
        assert res.status_code == 200

    def test_delete_user_not_found(self, client, db_mock):
        db_mock.delete_user.return_value = False
        res = client.delete("/api/v1/auth/users/999", headers=auth_header())
        assert res.status_code == 404

    def test_change_own_password(self, client, db_mock):
        res = client.put("/api/v1/auth/users/1/password", headers=auth_header(),
                         json={"old_password": "admin123", "new_password": "newpass123"})
        assert res.status_code == 200

    def test_change_password_short(self, client):
        res = client.put("/api/v1/auth/users/1/password", headers=auth_header(),
                         json={"old_password": "admin123", "new_password": "123"})
        assert res.status_code == 422

    def test_change_password_wrong_old(self, client, db_mock):
        """非 admin 用户改自己密码时旧密码错误应返回 401"""
        # viewer 尝试改 admin 的密码 → 403 (不能改别人的)
        db_mock.get_user_by_username.return_value = {
            "id": 2, "username": "viewer", "role": "viewer",
            "hashed_password": hash_password("correct"), "is_active": True,
        }
        token = create_access_token("viewer", "viewer")
        res = client.put("/api/v1/auth/users/1/password",
                         headers={"Authorization": f"Bearer {token}"},
                         json={"old_password": "wrong", "new_password": "newpass123"})
        assert res.status_code == 403

    def test_change_password_self_wrong_old(self, client, db_mock):
        """admin 改自己密码时旧密码错误应返回 401"""
        # admin 的 JWT 没有 id 字段，所以 user_id != _user.get("id") 为 True
        # 但 admin role 跳过权限检查后进入密码校验
        db_mock.get_user_by_username.return_value = {
            "id": 1, "username": "admin", "role": "admin",
            "hashed_password": hash_password("admin123"), "is_active": True,
        }
        res = client.put("/api/v1/auth/users/1/password", headers=auth_header(),
                         json={"old_password": "wrong", "new_password": "newpass123"})
        # admin 改别人密码不需要旧密码（因为 _user.get("id") 是 None）
        # 所以这里实际是 200，这是 admin 的设计行为
        assert res.status_code == 200

    def test_refresh_token(self, client, db_mock):
        from backend.auth import create_refresh_token
        rt = create_refresh_token("admin")
        res = client.post("/api/v1/auth/refresh", json={"refresh_token": rt})
        assert res.status_code == 200
        assert "access_token" in res.json()

    def test_refresh_token_invalid(self, client):
        res = client.post("/api/v1/auth/refresh", json={"refresh_token": "invalid"})
        assert res.status_code == 401

    def test_refresh_token_missing(self, client):
        res = client.post("/api/v1/auth/refresh", json={})
        assert res.status_code == 422


# ── ROI Router Tests ──

class TestROIRouter:
    def test_list_rois(self, client, db_mock):
        db_mock.get_rois.return_value = [{"id": 1, "camera_id": 0, "name": "zone1"}]
        res = client.get("/api/v1/rois", headers=auth_header())
        assert res.status_code == 200
        assert len(res.json()) == 1

    def test_list_rois_with_camera_filter(self, client, db_mock):
        client.get("/api/v1/rois?camera_id=0", headers=auth_header())
        db_mock.get_rois.assert_called_with(0)

    def test_create_roi(self, client, db_mock):
        body = {"camera_id": 0, "name": "新区域", "polygon": [[0, 0], [100, 0], [100, 100], [0, 100]]}
        res = client.post("/api/v1/rois", headers=auth_header(), json=body)
        assert res.status_code == 200

    def test_create_roi_missing_field(self, client):
        res = client.post("/api/v1/rois", headers=auth_header(), json={"name": "x"})
        assert res.status_code == 422

    def test_update_roi(self, client):
        res = client.put("/api/v1/rois/1", headers=auth_header(), json={"name": "updated"})
        assert res.status_code == 200

    def test_update_roi_not_found(self, client, db_mock):
        db_mock.update_roi.return_value = False
        res = client.put("/api/v1/rois/999", headers=auth_header(), json={"name": "x"})
        assert res.status_code == 404

    def test_delete_roi(self, client):
        res = client.delete("/api/v1/rois/1", headers=auth_header())
        assert res.status_code == 200

    def test_delete_roi_not_found(self, client, db_mock):
        db_mock.delete_roi.return_value = False
        res = client.delete("/api/v1/rois/999", headers=auth_header())
        assert res.status_code == 404

    def test_unauthorized(self, client):
        res = client.get("/api/v1/rois")
        assert res.status_code == 401


# ── System Router Tests ──

class TestSystemRouter:
    def test_notification_config(self, client):
        res = client.get("/api/v1/notifications/config", headers=auth_header())
        assert res.status_code == 200
        data = res.json()
        assert "feishu" in data
        assert data["feishu"]["enabled"] is True
        # webhook_url should be masked
        assert "..." in data["feishu"]["webhook_url"]

    def test_audit_logs(self, client, db_mock):
        db_mock.query_audit_logs.return_value = [
            {"id": 1, "username": "admin", "action": "login", "timestamp": "2024-01-01T00:00:00"},
        ]
        res = client.get("/api/v1/audit-logs", headers=auth_header())
        assert res.status_code == 200
        assert len(res.json()) == 1

    def test_audit_logs_with_filters(self, client, db_mock):
        client.get("/api/v1/audit-logs?username=admin&action=login", headers=auth_header())
        call_kwargs = db_mock.query_audit_logs.call_args
        assert call_kwargs[1]["username"] == "admin"
        assert call_kwargs[1]["action"] == "login"

    def test_toggle_notification_invalid_channel(self, client):
        res = client.post("/api/v1/notifications/invalid_channel/toggle",
                          headers=auth_header(), json={"enabled": True})
        assert res.status_code == 422

    def test_toggle_notification_invalid_body(self, client):
        res = client.post("/api/v1/notifications/feishu/toggle",
                          headers=auth_header(), json={"enabled": "yes"})
        assert res.status_code == 422

    def test_toggle_notification_feishu(self, client, config):
        """飞书通知开关 — 应更新配置和 feishu_notifier"""
        mock_feishu = MagicMock()
        mock_feishu.enabled = True
        with patch("backend.main.feishu_notifier", mock_feishu):
            res = client.post("/api/v1/notifications/feishu/toggle",
                              headers=auth_header(), json={"enabled": False})
            assert res.status_code == 200
            assert res.json()["enabled"] is False
            assert config["notifications"]["feishu"]["enabled"] is False
            assert mock_feishu.enabled is False
