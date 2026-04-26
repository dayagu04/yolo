"""
数据库操作测试模块
"""
import pytest
from datetime import datetime, timedelta


@pytest.mark.database
class TestDatabaseOperations:
    """数据库操作测试类"""

    def test_database_connection(self, db_manager):
        """测试数据库连接"""
        assert db_manager is not None
        session = db_manager.get_session()
        assert session is not None
        session.close()

    def test_create_tables(self, db_manager):
        """测试创建表结构"""
        db_manager.create_tables()
        # 验证表已创建（通过插入数据）
        alert_id = db_manager.create_alert(
            camera_id=0,
            person_count=1,
            new_track_ids=[1],
            message="测试"
        )
        assert alert_id > 0

    def test_create_alert(self, db_manager):
        """测试创建告警记录"""
        alert_id = db_manager.create_alert(
            camera_id=0,
            person_count=2,
            new_track_ids=[1, 2],
            screenshot_path="test/path.jpg",
            message="测试告警",
            level="high"
        )
        assert alert_id > 0

    def test_query_alerts(self, db_manager):
        """测试查询告警记录"""
        # 先插入测试数据
        db_manager.create_alert(camera_id=0, person_count=1, new_track_ids=[1])

        result = db_manager.query_alerts(limit=10)
        assert "alerts" in result
        assert "total" in result
        assert result["total"] > 0

    def test_query_alerts_pagination(self, db_manager):
        """测试分页查询"""
        # 插入多条数据
        for i in range(5):
            db_manager.create_alert(camera_id=0, person_count=1, new_track_ids=[i])

        # 测试分页
        page1 = db_manager.query_alerts(limit=2, offset=0)
        page2 = db_manager.query_alerts(limit=2, offset=2)

        assert len(page1["alerts"]) == 2
        assert len(page2["alerts"]) == 2
        assert page1["alerts"][0]["id"] != page2["alerts"][0]["id"]

    def test_query_alerts_by_camera(self, db_manager):
        """测试按摄像头筛选"""
        db_manager.create_alert(camera_id=0, person_count=1, new_track_ids=[1])
        db_manager.create_alert(camera_id=1, person_count=1, new_track_ids=[2])

        result = db_manager.query_alerts(camera_id=0)
        for alert in result["alerts"]:
            assert alert["camera_id"] == 0

    def test_query_alerts_by_level(self, db_manager):
        """测试按级别筛选"""
        db_manager.create_alert(camera_id=0, person_count=1, new_track_ids=[1], level="high")
        db_manager.create_alert(camera_id=0, person_count=1, new_track_ids=[2], level="low")

        result = db_manager.query_alerts(level="high")
        for alert in result["alerts"]:
            assert alert["level"] == "high"

    def test_query_alerts_by_time_range(self, db_manager):
        """测试按时间范围筛选"""
        now = datetime.now()
        start_time = now - timedelta(hours=1)
        end_time = now + timedelta(hours=1)

        db_manager.create_alert(camera_id=0, person_count=1, new_track_ids=[1])

        result = db_manager.query_alerts(
            start_time=start_time.isoformat(),
            end_time=end_time.isoformat()
        )
        assert result["total"] > 0

    def test_get_alert_by_id(self, db_manager):
        """测试根据 ID 获取告警"""
        alert_id = db_manager.create_alert(camera_id=0, person_count=1, new_track_ids=[1])
        alert = db_manager.get_alert_by_id(alert_id)

        assert alert is not None
        assert alert["id"] == alert_id

    def test_delete_old_alerts(self, db_manager):
        """测试删除旧告警"""
        # 插入测试数据
        db_manager.create_alert(camera_id=0, person_count=1, new_track_ids=[1])

        # 删除 30 天前的数据
        deleted_count = db_manager.delete_old_alerts(days=30)
        assert deleted_count >= 0

    @pytest.mark.boundary
    def test_create_alert_with_null_values(self, db_manager):
        """测试创建告警时的空值处理"""
        alert_id = db_manager.create_alert(
            camera_id=0,
            person_count=0,
            new_track_ids=[],
            screenshot_path=None,
            message=None
        )
        assert alert_id > 0

    @pytest.mark.boundary
    def test_query_with_invalid_limit(self, db_manager):
        """测试无效的 limit 参数"""
        # 超大 limit
        result = db_manager.query_alerts(limit=10000)
        assert len(result["alerts"]) <= 500  # 应该有最大限制

    @pytest.mark.boundary
    def test_query_with_negative_offset(self, db_manager):
        """测试负数 offset（应该被修正为0）"""
        result = db_manager.query_alerts(offset=-1)
        # 应该处理为 0，不抛出异常
        assert result is not None
        assert "alerts" in result

    @pytest.mark.exception
    def test_database_connection_failure(self, config):
        """测试数据库连接失败"""
        from backend.database import DatabaseManager

        bad_config = config["database"].copy()
        bad_config["host"] = "invalid_host"

        with pytest.raises(Exception):
            db = DatabaseManager(bad_config)
            db.get_session()

    @pytest.mark.performance
    def test_bulk_insert_performance(self, db_manager):
        """测试批量插入性能"""
        import time

        start = time.time()
        for i in range(100):
            db_manager.create_alert(camera_id=0, person_count=1, new_track_ids=[i])
        duration = time.time() - start

        assert duration < 10, f"批量插入100条耗时 {duration:.2f}s，超过10秒"

    @pytest.mark.performance
    def test_query_performance(self, db_manager):
        """测试查询性能"""
        import time

        # 先插入数据
        for i in range(50):
            db_manager.create_alert(camera_id=0, person_count=1, new_track_ids=[i])

        start = time.time()
        result = db_manager.query_alerts(limit=50)
        duration = time.time() - start

        assert duration < 1, f"查询50条耗时 {duration:.2f}s，超过1秒"
        assert len(result["alerts"]) > 0
