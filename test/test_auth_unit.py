"""auth.py 单元测试"""
import os
import time
import pytest
from unittest.mock import patch, MagicMock
from fastapi import HTTPException

# 设置测试密钥
os.environ["YOLO_AUTH_SECRET_KEY"] = "test_secret_key_for_unit_testing_only_32bytes!!"

from backend.auth import (
    hash_password, verify_password,
    check_login_allowed, record_login_failure, clear_login_failures,
    check_rate_limit,
    create_access_token, create_refresh_token, decode_token,
    _login_failures, _rate_limits, _MAX_ATTEMPTS, _LOCKOUT_SECONDS,
)


# ── 密码工具 ──

class TestPassword:
    def test_hash_and_verify(self):
        hashed = hash_password("mypassword")
        assert hashed != "mypassword"
        assert verify_password("mypassword", hashed) is True

    def test_verify_wrong_password(self):
        hashed = hash_password("mypassword")
        assert verify_password("wrongpassword", hashed) is False

    def test_different_hashes(self):
        h1 = hash_password("same")
        h2 = hash_password("same")
        assert h1 != h2  # bcrypt 每次生成不同的 salt


# ── 登录锁定 ──

class TestLoginLockout:
    def setup_method(self):
        _login_failures.clear()

    def test_no_lockout_initially(self):
        check_login_allowed("user1")  # 应该不抛异常

    def test_lockout_after_max_attempts(self):
        for _ in range(_MAX_ATTEMPTS):
            record_login_failure("user1")
        with pytest.raises(HTTPException) as exc_info:
            check_login_allowed("user1")
        assert exc_info.value.status_code == 429

    def test_clear_failures_resets(self):
        for _ in range(_MAX_ATTEMPTS):
            record_login_failure("user1")
        clear_login_failures("user1")
        check_login_allowed("user1")  # 应该不抛异常

    def test_lockout_expires(self):
        now = time.time()
        # 模拟过期的失败记录
        _login_failures["user1"] = [now - _LOCKOUT_SECONDS - 1] * _MAX_ATTEMPTS
        check_login_allowed("user1")  # 应该不抛异常，因为记录已过期

    def test_different_users_independent(self):
        for _ in range(_MAX_ATTEMPTS):
            record_login_failure("user1")
        check_login_allowed("user2")  # user2 不受影响


# ── 请求限流 ──

class TestRateLimit:
    def setup_method(self):
        _rate_limits.clear()

    def _mock_request(self, ip="127.0.0.1"):
        req = MagicMock()
        req.client.host = ip
        return req

    def test_within_limit(self):
        req = self._mock_request()
        for _ in range(5):
            check_rate_limit(req, max_requests=10, window=60)

    def test_exceeds_limit(self):
        req = self._mock_request()
        for _ in range(10):
            check_rate_limit(req, max_requests=10, window=60)
        with pytest.raises(HTTPException) as exc_info:
            check_rate_limit(req, max_requests=10, window=60)
        assert exc_info.value.status_code == 429

    def test_different_ips_independent(self):
        req1 = self._mock_request("1.1.1.1")
        req2 = self._mock_request("2.2.2.2")
        for _ in range(10):
            check_rate_limit(req1, max_requests=10, window=60)
        check_rate_limit(req2, max_requests=10, window=60)  # 不受影响

    def test_window_expiry(self):
        req = self._mock_request()
        now = time.time()
        _rate_limits["127.0.0.1"] = [now - 61] * 10  # 全部过期
        check_rate_limit(req, max_requests=10, window=60)  # 应该通过


# ── Token 工具 ──

class TestToken:
    def test_create_and_decode_access_token(self):
        token = create_access_token("admin", "admin", expire_minutes=60)
        payload = decode_token(token, expected_type="access")
        assert payload["sub"] == "admin"
        assert payload["role"] == "admin"
        assert payload["type"] == "access"

    def test_create_and_decode_refresh_token(self):
        token = create_refresh_token("user1", expire_days=7)
        payload = decode_token(token, expected_type="refresh")
        assert payload["sub"] == "user1"
        assert payload["type"] == "refresh"

    def test_decode_wrong_type(self):
        token = create_access_token("admin", "admin")
        with pytest.raises(HTTPException) as exc_info:
            decode_token(token, expected_type="refresh")
        assert exc_info.value.status_code == 401

    def test_decode_invalid_token(self):
        with pytest.raises(HTTPException) as exc_info:
            decode_token("invalid.token.here")
        assert exc_info.value.status_code == 401

    def test_decode_expired_token(self):
        token = create_access_token("admin", "admin", expire_minutes=-1)
        with pytest.raises(HTTPException):
            decode_token(token)

    def test_decode_missing_sub(self):
        from jose import jwt
        payload = {"role": "admin", "exp": time.time() + 3600, "type": "access"}
        token = jwt.encode(payload, os.environ["YOLO_AUTH_SECRET_KEY"], algorithm="HS256")
        with pytest.raises(HTTPException):
            decode_token(token)
