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


# ── 配置原子写入回归测试（M4） ──

@pytest.mark.unit
class TestSaveConfigAtomic:
    """save_config_atomic：写入原子化、并发安全、失败保护原文件"""

    def test_basic_write(self, tmp_path):
        from backend.config import save_config_atomic
        import yaml

        path = tmp_path / "config.yaml"
        save_config_atomic(path, {"server": {"port": 8000}, "auth": {"x": 1}})
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert loaded == {"server": {"port": 8000}, "auth": {"x": 1}}

    def test_replaces_existing_file(self, tmp_path):
        from backend.config import save_config_atomic
        import yaml

        path = tmp_path / "config.yaml"
        path.write_text("old: content\n", encoding="utf-8")
        save_config_atomic(path, {"new": "content"})
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert loaded == {"new": "content"}

    def test_failure_preserves_original(self, tmp_path, monkeypatch):
        """yaml.dump 抛异常时，原文件应保持不变，且不留临时文件"""
        from backend import config as config_mod

        path = tmp_path / "config.yaml"
        path.write_text("good: original\n", encoding="utf-8")

        def boom(*args, **kwargs):
            raise RuntimeError("simulated dump failure")

        monkeypatch.setattr(config_mod.yaml, "dump", boom)
        with pytest.raises(RuntimeError):
            config_mod.save_config_atomic(path, {"new": "content"})

        # 原文件未变
        assert path.read_text(encoding="utf-8") == "good: original\n"
        # 临时文件已清理
        leftovers = [p for p in tmp_path.iterdir() if p.name.startswith(".config.")]
        assert leftovers == [], f"残留临时文件: {leftovers}"

    def test_concurrent_writes_no_corruption(self, tmp_path):
        """多线程并发写入 config.yaml，最终文件必须是合法 YAML 且为某次写入的完整副本"""
        import threading
        import yaml
        from backend.config import save_config_atomic

        path = tmp_path / "config.yaml"
        N = 30
        payloads = [{"id": i, "data": "x" * 200, "list": list(range(50))} for i in range(N)]

        def write(p):
            save_config_atomic(path, p)

        threads = [threading.Thread(target=write, args=(p,)) for p in payloads]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # 最终文件必须能被 yaml 解析（原子替换，绝不会半截）
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert isinstance(loaded, dict)
        assert loaded in payloads


# ── 结构化日志线程安全（M3） ──

@pytest.mark.unit
class TestStructuredLoggerThreadSafety:
    def test_concurrent_log_and_read_no_exception(self):
        """并发写入与读取 _buffer 不应抛 RuntimeError，且无丢数据"""
        import threading
        from backend.logging_system import StructuredLogger

        logger = StructuredLogger(name=f"test_concurrent_{id(object())}", log_to_file=False)
        N_WRITERS = 4
        PER_WRITER = 50
        errors: list = []

        def writer(tid: int):
            try:
                for i in range(PER_WRITER):
                    logger.log("info", "evt", f"msg-{tid}-{i}")
            except Exception as e:
                errors.append(e)

        def reader():
            try:
                for _ in range(100):
                    _ = logger.get_recent_logs(limit=200)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=writer, args=(t,)) for t in range(N_WRITERS)]
        threads.append(threading.Thread(target=reader))
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == [], f"并发期间出现异常: {errors}"
        # 缓冲 maxlen=500，写入总数 200，应全部保留
        recent = logger.get_recent_logs(limit=500)
        assert len(recent) == N_WRITERS * PER_WRITER

    def test_sensitive_keys_redacted(self):
        """敏感字段（password/token/secret/api_key/authorization）必须被脱敏"""
        from backend.logging_system import StructuredLogger

        logger = StructuredLogger(name=f"test_sanitize_{id(object())}", log_to_file=False)
        payload = logger.log(
            "info", "evt", "test",
            data={"username": "alice", "password": "p@ss", "nested": {"api_key": "k", "ok": "v"}},
        )
        assert payload["data"]["username"] == "alice"
        assert payload["data"]["password"] == "***"
        assert payload["data"]["nested"]["api_key"] == "***"
        assert payload["data"]["nested"]["ok"] == "v"
