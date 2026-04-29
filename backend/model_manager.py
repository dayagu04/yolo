"""
多模型管理器
支持同时加载多个 YOLO 模型（人员检测、安全帽检测、车辆检测等）
"""
import logging
from pathlib import Path
from typing import Optional
from ultralytics import YOLO


class ModelManager:
    """管理多个 YOLO 模型实例"""

    def __init__(self, models_dir: str = "models"):
        self.models_dir = Path(models_dir)
        self.logger = logging.getLogger(__name__)
        self._models: dict[str, YOLO] = {}
        self._model_info: dict[str, dict] = {}

    def load_model(self, name: str, path: str, device: str = "cpu") -> bool:
        """加载指定模型"""
        try:
            model_path = Path(path)
            if not model_path.is_absolute():
                model_path = self.models_dir.parent / path

            model = YOLO(str(model_path))
            if device != "cpu":
                model.to(device)

            self._models[name] = model
            self._model_info[name] = {
                "name": name,
                "path": str(model_path),
                "device": device,
                "classes": list(model.names.values()) if hasattr(model, "names") else [],
                "num_classes": len(model.names) if hasattr(model, "names") else 0,
            }
            self.logger.info(f"模型 '{name}' 加载成功: {model_path}")
            return True
        except Exception as e:
            self.logger.error(f"模型 '{name}' 加载失败: {e}")
            return False

    def get_model(self, name: str) -> Optional[YOLO]:
        return self._models.get(name)

    def unload_model(self, name: str) -> bool:
        if name in self._models:
            del self._models[name]
            self._model_info.pop(name, None)
            self.logger.info(f"模型 '{name}' 已卸载")
            return True
        return False

    def list_models(self) -> list[dict]:
        return list(self._model_info.values())

    def scan_available(self) -> list[dict]:
        """扫描 models/ 目录下可用的模型文件"""
        available = []
        if self.models_dir.exists():
            for f in self.models_dir.iterdir():
                if f.suffix in (".pt", ".onnx", ".engine"):
                    available.append({
                        "filename": f.name,
                        "path": str(f),
                        "size_mb": round(f.stat().st_size / 1024 / 1024, 1),
                        "loaded": any(info["path"] == str(f) for info in self._model_info.values()),
                    })
        return available

    @property
    def loaded_count(self) -> int:
        return len(self._models)


# 全局模型管理器实例
model_manager = ModelManager()
