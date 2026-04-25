"""
配置管理模块
负责加载、校验 config.yaml，支持环境变量覆盖
"""
import os
import yaml
from pathlib import Path
from typing import Any, Dict, Optional
import logging


class ConfigError(Exception):
    """配置错误异常"""
    pass


class ConfigManager:
    """配置管理器"""

    # 必填项定义
    REQUIRED_FIELDS = {
        "database.host": str,
        "database.user": str,
        "database.password": str,
        "database.database": str,
    }

    # 范围校验规则
    RANGE_RULES = {
        "detection.conf_threshold": (0.1, 0.95),
        "detection.detect_every_n": (1, 10),
        "alert.cooldown_sec": (0.5, 60.0),
        "alert.screenshot.quality": (50, 95),
        "alert.screenshot.retention_days": (1, 365),
    }

    def __init__(self, config_path: Path):
        self.config_path = config_path
        self.logger = logging.getLogger(__name__)
        self._config: Dict[str, Any] = {}

    def load(self) -> Dict[str, Any]:
        """加载并校验配置"""
        # 1. 加载 YAML
        if not self.config_path.exists():
            raise ConfigError(f"配置文件不存在: {self.config_path}")

        with open(self.config_path, "r", encoding="utf-8") as f:
            self._config = yaml.safe_load(f)

        if not isinstance(self._config, dict):
            raise ConfigError("配置文件格式错误：根节点必须是字典")

        # 2. 环境变量覆盖
        self._apply_env_overrides()

        # 3. 必填项校验
        self._validate_required()

        # 4. 范围校验
        self._validate_ranges()

        self.logger.info(f"配置加载成功: {len(self._config)} 个配置项")
        return self._config

    def _apply_env_overrides(self):
        """应用环境变量覆盖（YOLO_{SECTION}_{KEY} 格式）"""
        for env_key, env_value in os.environ.items():
            if not env_key.startswith("YOLO_"):
                continue

            # YOLO_DATABASE_PASSWORD -> database.password
            parts = env_key[5:].lower().split("_")
            if len(parts) < 2:
                continue

            section = parts[0]
            key = "_".join(parts[1:])

            if section not in self._config:
                self._config[section] = {}

            # 类型转换
            if env_value.lower() in ("true", "false"):
                self._config[section][key] = env_value.lower() == "true"
            elif env_value.isdigit():
                self._config[section][key] = int(env_value)
            elif self._is_float(env_value):
                self._config[section][key] = float(env_value)
            else:
                self._config[section][key] = env_value

            self.logger.info(f"环境变量覆盖: {section}.{key} = {env_value}")

    @staticmethod
    def _is_float(s: str) -> bool:
        try:
            float(s)
            return True
        except ValueError:
            return False

    def _get_nested(self, path: str) -> Optional[Any]:
        """获取嵌套配置值（database.host -> config['database']['host']）"""
        parts = path.split(".")
        value = self._config
        for part in parts:
            if not isinstance(value, dict) or part not in value:
                return None
            value = value[part]
        return value

    def _validate_required(self):
        """校验必填项"""
        errors = []
        for field, expected_type in self.REQUIRED_FIELDS.items():
            value = self._get_nested(field)
            if value is None:
                errors.append(f"缺少必填项: {field}")
            elif not isinstance(value, expected_type):
                errors.append(
                    f"类型错误: {field} 应为 {expected_type.__name__}，实际为 {type(value).__name__}"
                )

        if errors:
            raise ConfigError("配置校验失败:\n  - " + "\n  - ".join(errors))

    def _validate_ranges(self):
        """校验范围"""
        errors = []
        for field, (min_val, max_val) in self.RANGE_RULES.items():
            value = self._get_nested(field)
            if value is None:
                continue  # 可选项，跳过

            if not isinstance(value, (int, float)):
                errors.append(f"类型错误: {field} 应为数值类型")
                continue

            if not (min_val <= value <= max_val):
                errors.append(
                    f"范围错误: {field} = {value}，应在 [{min_val}, {max_val}] 范围内"
                )

        if errors:
            raise ConfigError("配置校验失败:\n  - " + "\n  - ".join(errors))


def load_and_validate_config(config_path: Path) -> Dict[str, Any]:
    """加载并校验配置（便捷函数）"""
    manager = ConfigManager(config_path)
    return manager.load()
