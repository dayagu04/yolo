"""
Redis 统计和日志系统单元测试
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path
import sys

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from backend.logging_system import StructuredLogger


@pytest.mark.unit
class TestStructuredLogger:
    """结构化日志系统单元测试"""

    @pytest.fixture
    def logger(self):
        return StructuredLogger(name="test_logger", max_entries=100)

    def test_logger_init(self, logger):
        """测试日志器初始化"""
        assert logger._buffer.maxlen == 100
        assert len(logger._buffer) == 0

    def test_log_info(self, logger):
        """测试记录 info 日志"""
        entry = logger.log("info", "test.event", "测试消息")

        assert entry["level"] == "info"
        assert entry["event"] == "test.event"
        assert entry["message"] == "测试消息"
        assert "timestamp" in entry

    def test_log_with_camera_id(self, logger):
        """测试带摄像头 ID 的日志"""
        entry = logger.log("info", "camera.event", "摄像头消息", camera_id=0)

        assert entry["camera_id"] == 0

    def test_log_with_data(self, logger):
        """测试带数据的日志"""
        data = {"key": "value", "count": 5}
        entry = logger.log("info", "test.event", "消息", data=data)

        assert entry["data"] == data

    def test_log_levels(self, logger):
        """测试所有日志级别"""
        for level in ["debug", "info", "warning", "error"]:
            entry = logger.log(level, "test.event", "消息")
            assert entry["level"] == level

    def test_buffer_limit(self, logger):
        """测试缓冲区限制"""
        for i in range(150):
            logger.log("info", "test.event", f"消息 {i}")

        # 缓冲区不应超过最大值
        assert len(logger._buffer) <= 100

    def test_get_recent_logs(self, logger):
        """测试获取最近日志"""
        for i in range(20):
            logger.log("info", "test.event", f"消息 {i}")

        logs = logger.get_recent_logs(10)

        assert len(logs) == 10

    def test_get_recent_logs_all(self, logger):
        """测试获取所有日志"""
        for i in range(5):
            logger.log("info", "test.event", f"消息 {i}")

        logs = logger.get_recent_logs(100)

        assert len(logs) == 5

    def test_iso_now_format(self, logger):
        """测试时间戳格式"""
        ts = logger._iso_now()

        # 应该是 ISO 8601 格式
        from datetime import datetime
        datetime.fromisoformat(ts)  # 不抛出异常即为正确格式

    @pytest.mark.boundary
    def test_log_empty_message(self, logger):
        """测试空消息"""
        entry = logger.log("info", "test.event", "")

        assert entry["message"] == ""

    @pytest.mark.boundary
    def test_log_long_message(self, logger):
        """测试超长消息"""
        long_message = "x" * 10000
        entry = logger.log("info", "test.event", long_message)

        assert entry["message"] == long_message

    @pytest.mark.boundary
    def test_log_special_characters(self, logger):
        """测试特殊字符"""
        special_msg = "消息 with <script>alert('xss')</script> & 'quotes'"
        entry = logger.log("info", "test.event", special_msg)

        assert entry["message"] == special_msg

    @pytest.mark.boundary
    def test_get_recent_logs_zero(self, logger):
        """测试获取 0 条日志（会被限制为 1）"""
        logger.log("info", "test.event", "消息")
        logs = logger.get_recent_logs(0)

        # 实际实现会将 0 限制为 1
        assert len(logs) == 1

    @pytest.mark.boundary
    def test_get_recent_logs_negative(self, logger):
        """测试获取负数条日志（会被限制为 1）"""
        logger.log("info", "test.event", "消息")
        logs = logger.get_recent_logs(-1)

        # 实际实现会将负数限制为 1
        assert len(logs) == 1


@pytest.mark.unit
class TestRedisStats:
    """Redis 统计单元测试"""

    @pytest.fixture
    def redis_config(self):
        return {
            "enabled": True,
            "host": "localhost",
            "port": 6379,
            "password": "",
            "db": 0,
            "decode_responses": True
        }

    def test_redis_disabled(self):
        """测试 Redis 禁用"""
        from backend.redis_stats import RedisStats

        config = {"enabled": False}
        redis = RedisStats(config)

        assert redis.is_enabled() is False

    @patch('redis.Redis')
    def test_redis_connection(self, mock_redis, redis_config):
        """测试 Redis 连接"""
        from backend.redis_stats import RedisStats

        mock_client = Mock()
        mock_client.ping.return_value = True
        mock_redis.return_value = mock_client

        redis = RedisStats(redis_config)

        assert redis.is_enabled() is True

    @patch('redis.Redis')
    def test_incr_today_alerts(self, mock_redis, redis_config):
        """测试增加今日告警计数"""
        from backend.redis_stats import RedisStats

        mock_client = Mock()
        mock_client.ping.return_value = True
        mock_client.incr.return_value = 1
        mock_redis.return_value = mock_client

        redis = RedisStats(redis_config)
        redis.incr_today_alerts(camera_id=0)

        mock_client.incr.assert_called()

    @patch('redis.Redis')
    def test_update_current_persons(self, mock_redis, redis_config):
        """测试更新当前人数"""
        from backend.redis_stats import RedisStats

        mock_client = Mock()
        mock_client.ping.return_value = True
        mock_redis.return_value = mock_client

        redis = RedisStats(redis_config)
        redis.update_current_persons(camera_id=0, count=5)

        mock_client.hset.assert_called()

    @patch('redis.Redis')
    def test_get_today_alerts(self, mock_redis, redis_config):
        """测试获取今日告警数"""
        from backend.redis_stats import RedisStats

        mock_client = Mock()
        mock_client.ping.return_value = True
        mock_client.get.return_value = "10"
        mock_redis.return_value = mock_client

        redis = RedisStats(redis_config)
        count = redis.get_today_alerts()

        assert count == 10

    @patch('redis.Redis')
    def test_get_all_stats(self, mock_redis, redis_config):
        """测试获取所有统计"""
        from backend.redis_stats import RedisStats

        mock_client = Mock()
        mock_client.ping.return_value = True
        mock_client.get.return_value = "5"
        mock_client.hgetall.return_value = {"0": "3"}
        mock_client.smembers.return_value = {"0"}
        mock_redis.return_value = mock_client

        redis = RedisStats(redis_config)
        stats = redis.get_all_stats()

        assert "today_alerts" in stats
        assert "online_cameras" in stats

    @patch('redis.Redis')
    def test_set_camera_online(self, mock_redis, redis_config):
        """测试设置摄像头在线"""
        from backend.redis_stats import RedisStats

        mock_client = Mock()
        mock_client.ping.return_value = True
        mock_redis.return_value = mock_client

        redis = RedisStats(redis_config)
        redis.set_camera_online(camera_id=0)

        mock_client.sadd.assert_called()

    @patch('redis.Redis')
    def test_set_camera_offline(self, mock_redis, redis_config):
        """测试设置摄像头离线"""
        from backend.redis_stats import RedisStats

        mock_client = Mock()
        mock_client.ping.return_value = True
        mock_redis.return_value = mock_client

        redis = RedisStats(redis_config)
        redis.set_camera_offline(camera_id=0)

        mock_client.srem.assert_called()

    @pytest.mark.exception
    @patch('redis.Redis')
    def test_redis_connection_failure(self, mock_redis, redis_config):
        """测试 Redis 连接失败"""
        from backend.redis_stats import RedisStats

        mock_redis.side_effect = Exception("Connection refused")

        redis = RedisStats(redis_config)

        assert redis.is_enabled() is False

    @pytest.mark.exception
    @patch('redis.Redis')
    def test_operation_on_disconnected(self, mock_redis, redis_config):
        """测试断开连接时的操作"""
        from backend.redis_stats import RedisStats

        mock_client = Mock()
        mock_client.ping.return_value = True
        mock_client.incr.side_effect = Exception("Connection lost")
        mock_redis.return_value = mock_client

        redis = RedisStats(redis_config)

        # 不应该抛出异常
        redis.incr_today_alerts(camera_id=0)
