"""
目标检测模块

负责 YOLO 模型加载、推理、结果缓存，与视频流采集解耦。
"""
import time
from pathlib import Path
from typing import Optional
import numpy as np
import cv2


class InferenceCache:
    """推理缓存：场景未变化时复用检测结果，降低 GPU 负载"""

    def __init__(self, max_age_sec: float = 1.0, scene_change_threshold: float = 5.0):
        self.enabled = True
        self.max_age_sec = max_age_sec
        self.scene_change_threshold = scene_change_threshold

        self._last_results = None
        self._last_frame = None  # 存储原始帧，避免 M6（plot 在旧帧上绘制）
        self._last_ts = 0.0
        self._prev_gray = None

    def should_skip_inference(self, frame: np.ndarray, now_ts: float) -> bool:
        """判断是否可以跳过推理（场景未变化）"""
        if not self.enabled or self._last_results is None:
            return False

        if now_ts - self._last_ts >= self.max_age_sec:
            return False

        if self._prev_gray is None:
            return False

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        diff = cv2.absdiff(self._prev_gray, gray)
        return np.mean(diff) < self.scene_change_threshold

    def update(self, frame: np.ndarray, results, now_ts: float):
        """更新缓存"""
        self._last_frame = frame.copy()
        self._last_results = results
        self._last_ts = now_ts
        self._prev_gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

    def get_cached_results(self):
        """获取缓存结果（原始帧 + YOLO results）"""
        return self._last_frame, self._last_results


class ObjectDetector:
    """YOLO 目标检测器（线程安全，支持动态模型重载）"""

    def __init__(
        self,
        model_path: str = "models/yolov8n.pt",
        device: str = "cpu",
        conf_threshold: float = 0.5,
        cache_enabled: bool = True,
        cache_max_age_sec: float = 1.0,
        scene_change_threshold: float = 5.0,
    ):
        self.model_path = Path(model_path)
        self.device = device
        self.conf_threshold = conf_threshold

        self._model = None
        self._model_loaded = False
        self._last_error: Optional[str] = None

        self.cache = InferenceCache(cache_max_age_sec, scene_change_threshold) if cache_enabled else None

    def load_model(self) -> bool:
        """加载 YOLO 模型"""
        try:
            from ultralytics import YOLO
            self._model = YOLO(str(self.model_path))
            if self.device.startswith("cuda"):
                self._model.to(self.device)
            self._model_loaded = True
            self._last_error = None
            return True
        except Exception as e:
            self._last_error = f"模型加载失败: {e}"
            self._model = None
            self._model_loaded = False
            return False

    def reload_model(self, model_path: Optional[str] = None) -> bool:
        """重新加载模型（支持动态切换）"""
        if model_path:
            self.model_path = Path(model_path)

        old_model = self._model
        self._model = None
        self._model_loaded = False

        success = self.load_model()
        if not success and old_model is not None:
            # 回滚
            self._model = old_model
            self._model_loaded = True

        return success

    def detect(self, frame: np.ndarray, detect_every_n: int = 1, frame_count: int = 0) -> tuple:
        """
        执行目标检测

        Args:
            frame: 输入帧
            detect_every_n: 每 N 帧检测一次
            frame_count: 当前帧号

        Returns:
            (annotated_frame, person_count, results, error)
            - M6 修复：缓存命中时仍返回当前帧的标注图，避免闪烁
            - M5 修复：推理异常时 error 非 None，调用方可感知并暂停告警
        """
        if self._model is None:
            return frame, 0, None, self._last_error

        # 跳帧优化
        if frame_count % detect_every_n != 0:
            return frame, 0, None, None

        now_ts = time.time()

        # 缓存命中检查
        if self.cache and self.cache.should_skip_inference(frame, now_ts):
            cached_frame, cached_results = self.cache.get_cached_results()
            # M6 修复：在当前帧上重新绘制缓存的检测框，而非返回旧帧的 plot
            person_count = self._count_persons(cached_results)
            annotated = self._draw_results(frame, cached_results)
            return annotated, person_count, cached_results, None

        # 执行推理（捕获异常，M5 修复）
        try:
            results = self._model(frame, verbose=False, conf=self.conf_threshold)
            person_count = self._count_persons(results)

            # 更新缓存
            if self.cache:
                self.cache.update(frame, results, now_ts)

            annotated = results[0].plot()
            return annotated, person_count, results, None

        except Exception as e:
            error_msg = f"推理失败: {e}"
            self._last_error = error_msg
            return frame, 0, None, error_msg

    def _count_persons(self, results) -> int:
        """统计 person 类别数量"""
        if results is None:
            return 0
        boxes = results[0].boxes
        if boxes is None:
            return 0
        # YOLO person 类别 ID 为 0
        return int(sum(1 for cls in boxes.cls if int(cls) == 0))

    def _draw_results(self, frame: np.ndarray, results) -> np.ndarray:
        """在指定帧上绘制检测结果（M6 修复的关键）"""
        if results is None:
            return frame

        # 手动绘制 bbox（避免 plot() 在旧帧上绘制）
        annotated = frame.copy()
        boxes = results[0].boxes
        if boxes is not None:
            for box in boxes:
                x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                cls_id = int(box.cls[0])
                conf = float(box.conf[0])

                # 只绘制 person (cls=0)
                if cls_id == 0:
                    cv2.rectangle(annotated, (int(x1), int(y1)), (int(x2), int(y2)), (0, 255, 0), 2)
                    label = f"person {conf:.2f}"
                    cv2.putText(annotated, label, (int(x1), int(y1) - 10),
                               cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)

        return annotated

    def set_conf_threshold(self, conf: float):
        """动态调整置信度阈值"""
        self.conf_threshold = max(0.0, min(1.0, conf))

    def is_loaded(self) -> bool:
        return self._model_loaded

    def get_last_error(self) -> Optional[str]:
        return self._last_error
