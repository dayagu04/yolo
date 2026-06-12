"""
视频采集模块

负责 OpenCV VideoCapture 的连接管理、帧读取、重连逻辑，与推理解耦。
"""
import time
from typing import Optional, Union
import cv2
import numpy as np


class VideoCapture:
    """线程安全的视频流采集器（支持摄像头/RTSP）"""

    def __init__(
        self,
        source: Union[int, str],
        width: Optional[int] = None,
        height: Optional[int] = None,
        reconnect_interval_sec: float = 5.0,
        connection_timeout_sec: float = 10.0,
    ):
        """
        Args:
            source: 摄像头 ID (0/1/...) 或 RTSP URL
            width: 目标分辨率宽度（None = 自动）
            height: 目标分辨率高度（None = 自动）
            reconnect_interval_sec: 断开后重连间隔
            connection_timeout_sec: 连接超时
        """
        self.source = source
        self.width = width
        self.height = height
        self.reconnect_interval_sec = reconnect_interval_sec
        self.connection_timeout_sec = connection_timeout_sec

        self._cap: Optional[cv2.VideoCapture] = None
        self._connected = False
        self._last_reconnect_attempt = 0.0

    def open(self) -> bool:
        """打开视频流（支持本地摄像头/RTSP）"""
        try:
            self._cap = cv2.VideoCapture(self.source)

            # RTSP 低延迟配置
            if isinstance(self.source, str) and self.source.startswith("rtsp"):
                self._cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

            # 设置分辨率
            if self.width and self.height:
                self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
                self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)

            # 验证连接
            if not self._cap.isOpened():
                self.close()
                return False

            # 读取一帧验证流可用
            ret, _ = self._cap.read()
            if not ret:
                self.close()
                return False

            self._connected = True
            return True

        except Exception as e:
            self.close()
            return False

    def close(self):
        """关闭视频流"""
        if self._cap is not None:
            self._cap.release()
            self._cap = None
        self._connected = False

    def read_frame(self) -> tuple[bool, Optional[np.ndarray]]:
        """
        读取一帧（带自动重连）

        Returns:
            (success, frame) - success=False 时触发重连逻辑
        """
        if self._cap is None or not self._connected:
            # 尝试重连
            if self._should_attempt_reconnect():
                self._last_reconnect_attempt = time.time()
                if self.open():
                    return self.read_frame()
            return False, None

        ret, frame = self._cap.read()

        if not ret:
            # 读取失败，标记断开，下次循环重连
            self._connected = False
            return False, None

        return True, frame

    def _should_attempt_reconnect(self) -> bool:
        """判断是否应该尝试重连（避免频繁重连）"""
        now = time.time()
        return (now - self._last_reconnect_attempt) >= self.reconnect_interval_sec

    def is_connected(self) -> bool:
        return self._connected

    def get_resolution(self) -> tuple[int, int]:
        """获取当前分辨率"""
        if self._cap is None:
            return (0, 0)
        w = int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        return (w, h)

    def get_fps(self) -> float:
        """获取视频流 FPS（仅供参考）"""
        if self._cap is None:
            return 0.0
        return self._cap.get(cv2.CAP_PROP_FPS)
