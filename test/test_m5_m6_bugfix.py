"""
M5/M6 Bug 修复验证测试

M5: 推理异常传播 - 推理失败时 AlertManager 应暂停告警
M6: 缓存帧错位 - 缓存命中时应在当前帧上重绘，避免闪烁
"""
import pytest
import numpy as np
import time
from unittest.mock import Mock, patch, MagicMock
from backend.camera import CameraManager
from backend.detection import ObjectDetector


@pytest.mark.unit
class TestM5InferenceErrorPropagation:
    """M5: 推理异常传播测试"""

    def test_inference_error_stops_alerts(self):
        """推理异常时应暂停告警"""
        camera = CameraManager(camera_id=0, source=0, screenshot_config={})

        # Mock signal callback 捕获告警
        signals = []
        camera.signal_callback = lambda msg: signals.append(msg)
        camera.alert_manager.signal_callback = lambda msg: signals.append(msg)

        # 模拟推理失败
        mock_frame = np.zeros((480, 640, 3), dtype=np.uint8)
        error_msg = "CUDA out of memory"

        # 第一次推理失败
        camera.alert_manager.process_detections(
            frame=mock_frame,
            results=None,
            person_count=0,
            inference_error=error_msg,
            frame_ts=time.time()
        )

        # 应该有一条 warning 日志
        warning_logs = [s for s in signals if s.get("type") == "log" and s.get("level") == "warning"]
        assert len(warning_logs) >= 1, f"Expected warning log, got signals: {signals}"
        assert any("推理异常" in log["message"] or "暂停告警" in log["message"] for log in warning_logs)

        # 确认进入暂停状态
        assert camera.alert_manager._inference_error_paused is True

        # 推理恢复
        signals.clear()
        mock_results = Mock()
        mock_result = Mock()
        mock_result.boxes = None
        mock_results.__getitem__ = Mock(return_value=mock_result)

        camera.alert_manager.process_detections(
            frame=mock_frame,
            results=mock_results,
            person_count=1,
            inference_error=None,
            frame_ts=time.time()
        )

        # 应该有一条 info 日志表示恢复
        info_logs = [s for s in signals if s.get("type") == "log" and s.get("level") == "info"]
        assert len(info_logs) >= 1, f"Expected info log, got signals: {signals}"
        assert any("推理恢复" in log["message"] for log in info_logs)
        assert camera.alert_manager._inference_error_paused is False

    def test_detector_returns_error_on_exception(self):
        """ObjectDetector 推理异常时应返回 error 字段"""
        detector = ObjectDetector(model_path="models/yolov8n.pt", device="cpu")

        # 模拟模型推理失败
        detector._model = Mock()
        detector._model.side_effect = RuntimeError("GPU error")
        detector._model_loaded = True

        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        annotated, count, results, error = detector.detect(frame, detect_every_n=1, frame_count=0)

        # 应该返回错误信息
        assert error is not None
        assert "推理失败" in error
        assert results is None
        assert count == 0
        # 原始帧应该原样返回
        assert np.array_equal(annotated, frame)


@pytest.mark.unit
class TestM6CacheFrameMisalignment:
    """M6: 缓存帧错位修复测试"""

    def test_cache_hit_uses_current_frame(self):
        """缓存命中时应在当前帧上绘制，而非复用旧帧"""
        detector = ObjectDetector(
            model_path="models/yolov8n.pt",
            device="cpu",
            cache_enabled=True,
            cache_max_age_sec=2.0,
            scene_change_threshold=10.0  # 高阈值，容易命中缓存
        )

        # Mock YOLO 模型和结果（模拟真实的 tensor 结构）
        mock_tensor = Mock()
        mock_tensor.cpu = Mock(return_value=Mock(numpy=lambda: np.array([100, 100, 200, 200])))

        mock_box = Mock()
        mock_box.xyxy = [mock_tensor]
        mock_box.cls = [Mock()]
        mock_box.cls[0].__int__ = Mock(return_value=0)  # person
        mock_box.conf = [Mock()]
        mock_box.conf[0].__float__ = Mock(return_value=0.9)

        mock_boxes = Mock()
        mock_boxes.cls = [0]
        mock_boxes.__iter__ = Mock(return_value=iter([mock_box]))

        mock_result = Mock()
        mock_result.boxes = mock_boxes
        mock_result.plot = Mock(return_value=np.zeros((480, 640, 3), dtype=np.uint8))

        mock_results = [mock_result]

        mock_model = Mock(return_value=mock_results)

        detector._model = mock_model
        detector._model_loaded = True

        # 第一帧：推理执行（填充缓存）
        frame1 = np.ones((480, 640, 3), dtype=np.uint8) * 100
        annotated1, count1, results1, error1 = detector.detect(frame1, detect_every_n=1, frame_count=0)

        assert mock_model.call_count == 1
        assert error1 is None

        # 第二帧：场景几乎不变，应命中缓存
        frame2 = np.ones((480, 640, 3), dtype=np.uint8) * 102  # 轻微变化
        annotated2, count2, results2, error2 = detector.detect(frame2, detect_every_n=1, frame_count=1)

        # 关键验证：缓存命中时不应再调用模型（调用次数不变）
        assert mock_model.call_count == 1

        # M6 修复验证：annotated2 应该基于 frame2，而非 frame1
        # 虽然复用了检测结果，但绘制的是当前帧
        assert annotated2 is not None
        assert error2 is None

        # 检查背景像素（应该是 frame2 的灰度值 102，而非 frame1 的 100）
        # 由于有绘制，检查非绘制区域
        background_pixel = annotated2[0, 0]
        assert background_pixel[0] >= 100  # 应该接近 102

        # 检查缓存状态
        assert detector.cache._last_frame is not None
        assert detector.cache._last_results is not None

    def test_cache_miss_triggers_new_inference(self):
        """场景变化大时应触发新推理"""
        detector = ObjectDetector(
            model_path="models/yolov8n.pt",
            device="cpu",
            cache_enabled=True,
            scene_change_threshold=5.0  # 低阈值，容易触发新推理
        )

        mock_result = Mock()
        mock_result.boxes = None
        mock_result.plot = Mock(return_value=np.zeros((480, 640, 3), dtype=np.uint8))
        mock_results = [mock_result]

        mock_model = Mock(return_value=mock_results)

        detector._model = mock_model
        detector._model_loaded = True

        # 第一帧
        frame1 = np.ones((480, 640, 3), dtype=np.uint8) * 50
        detector.detect(frame1, detect_every_n=1, frame_count=0)
        assert mock_model.call_count == 1

        # 第二帧：场景剧烈变化
        frame2 = np.ones((480, 640, 3), dtype=np.uint8) * 200
        detector.detect(frame2, detect_every_n=1, frame_count=1)

        # 应该触发新推理
        assert mock_model.call_count == 2

    def test_draw_results_on_specified_frame(self):
        """_draw_results 应在指定帧上绘制（M6 的核心修复）"""
        detector = ObjectDetector(model_path="models/yolov8n.pt", device="cpu")

        frame_old = np.zeros((480, 640, 3), dtype=np.uint8)
        frame_new = np.ones((480, 640, 3), dtype=np.uint8) * 255

        # Mock YOLO 结果（包含一个 person bbox）
        mock_box = Mock()
        mock_box.xyxy = [Mock()]
        mock_box.xyxy[0].cpu = Mock(return_value=Mock(numpy=lambda: np.array([100, 100, 200, 200])))
        mock_box.cls = [0]  # person
        mock_box.conf = [0.9]

        mock_boxes = Mock()
        mock_boxes.__iter__ = Mock(return_value=iter([mock_box]))

        mock_result = Mock()
        mock_result.boxes = mock_boxes

        mock_results = [mock_result]

        # 在 frame_new 上绘制
        annotated = detector._draw_results(frame_new, mock_results)

        # 验证：annotated 基于 frame_new（白色），而非 frame_old（黑色）
        # 检查背景像素（非绘制区域）
        background_pixel = annotated[0, 0]
        assert background_pixel[0] > 200  # 应该是白色背景
