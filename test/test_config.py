"""
配置管理测试模块
"""
import pytest
from pathlib import Path

ROOT = Path(__file__).parent.parent


@pytest.mark.unit
class TestConfigManagement:
    """配置管理测试类"""

    def test_load_main_config(self, config):
        """测试加载主配置文件"""
        assert config is not None
        assert isinstance(config, dict)
        assert len(config) > 0

    def test_required_fields(self, config):
        """测试必填配置项"""
        required = ["database", "detection", "alert", "server"]
        for field in required:
            assert field in config, f"缺少必填项: {field}"

    def test_secrets_config_exists(self):
        """测试敏感配置文件"""
        secrets_path = ROOT / "config.secrets.yaml"
        # 敏感配置是可选的
        if secrets_path.exists():
            assert secrets_path.is_file()

    def test_config_types(self, config):
        """测试配置项类型"""
        assert isinstance(config.get("database", {}).get("port"), int)
        assert isinstance(config.get("detection", {}).get("conf_threshold"), (int, float))
        assert isinstance(config.get("server", {}).get("host"), str)
        assert isinstance(config.get("server", {}).get("port"), int)

    def test_config_ranges(self, config):
        """测试配置范围"""
        conf_threshold = config.get("detection", {}).get("conf_threshold", 0.5)
        assert 0.1 <= conf_threshold <= 0.95, "conf_threshold 超出范围"

        port = config.get("server", {}).get("port", 8000)
        assert 1024 <= port <= 65535, "端口号超出范围"

    def test_camera_config(self, config):
        """测试摄像头配置"""
        cameras = config.get("cameras", [])
        if cameras:
            for cam in cameras:
                assert "id" in cam, "摄像头缺少 id"
                assert "source" in cam, "摄像头缺少 source"
                assert isinstance(cam["id"], int)

    @pytest.mark.boundary
    def test_invalid_config_path(self):
        """测试无效配置路径"""
        from backend.config import load_and_validate_config, ConfigError

        with pytest.raises((FileNotFoundError, ConfigError)):
            load_and_validate_config(ROOT / "nonexistent.yaml")

    @pytest.mark.boundary
    def test_empty_config(self, tmp_path):
        """测试空配置文件"""
        from backend.config import load_and_validate_config, ConfigError

        empty_config = tmp_path / "empty.yaml"
        empty_config.write_text("")

        with pytest.raises(ConfigError):
            load_and_validate_config(empty_config)

    @pytest.mark.boundary
    def test_malformed_yaml(self, tmp_path):
        """测试格式错误的 YAML"""
        from backend.config import load_and_validate_config

        bad_yaml = tmp_path / "bad.yaml"
        bad_yaml.write_text("invalid: yaml: content: [")

        with pytest.raises(Exception):
            load_and_validate_config(bad_yaml)

    def test_database_config_complete(self, config):
        """测试数据库配置完整性"""
        db_config = config.get("database", {})
        required_db_fields = ["host", "port", "user", "password", "database"]
        for field in required_db_fields:
            assert field in db_config, f"数据库配置缺少: {field}"
