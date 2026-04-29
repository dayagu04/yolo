"""
多进程摄像头采集模块
每路摄像头独立进程采集，通过共享内存传递帧数据，避免 GIL 瓶颈
"""
import multiprocessing as mp
import time
import cv2
import numpy as np
from multiprocessing import shared_memory
from typing import Optional


class CaptureProcess:
    """摄像头采集进程管理器"""

    def __init__(self, camera_id: int, source, width: int = 640, height: int = 480):
        self.camera_id = camera_id
        self.source = source
        self.width = width
        self.height = height
        self._process: Optional[mp.Process] = None
        self._shm: Optional[shared_memory.SharedMemory] = None
        self._stop_event: Optional[mp.Event] = None
        self._frame_shape = (height, width, 3)
        self._frame_size = np.prod(self._frame_shape) * np.uint8().itemsize

    def start(self) -> bool:
        """启动采集进程"""
        try:
            # 创建共享内存
            self._shm = shared_memory.SharedMemory(create=True, size=self._frame_size)
            self._stop_event = mp.Event()

            self._process = mp.Process(
                target=_capture_loop,
                args=(
                    self.camera_id, self.source, self.width, self.height,
                    self._shm.name, self._stop_event,
                ),
                daemon=True,
            )
            self._process.start()
            return True
        except Exception as e:
            print(f"[CAM {self.camera_id}] 采集进程启动失败: {e}")
            return False

    def read_frame(self) -> Optional[np.ndarray]:
        """从共享内存读取最新帧"""
        if not self._shm:
            return None
        try:
            frame = np.ndarray(self._frame_shape, dtype=np.uint8, buffer=self._shm.buf)
            return frame.copy()
        except Exception:
            return None

    def stop(self):
        """停止采集进程"""
        if self._stop_event:
            self._stop_event.set()
        if self._process and self._process.is_alive():
            self._process.join(timeout=3)
        if self._shm:
            self._shm.close()
            self._shm.unlink()
            self._shm = None

    @property
    def is_alive(self) -> bool:
        return self._process is not None and self._process.is_alive()


def _capture_loop(
    camera_id: int, source, width: int, height: int,
    shm_name: str, stop_event: mp.Event,
):
    """采集进程主循环（在独立进程中运行）"""
    # 连接到已有的共享内存
    shm = shared_memory.SharedMemory(name=shm_name)
    frame_shape = (height, width, 3)
    shared_frame = np.ndarray(frame_shape, dtype=np.uint8, buffer=shm.buf)

    is_rtsp = isinstance(source, str) and source.lower().startswith("rtsp")
    cap = cv2.VideoCapture(source) if is_rtsp else cv2.VideoCapture(int(source), cv2.CAP_DSHOW)

    if not cap.isOpened():
        print(f"[CAM {self.camera_id}] 无法打开摄像头: {source}")
        shm.close()
        return

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)

    # 丢弃预热帧
    for _ in range(5):
        cap.read()

    print(f"[CAM {self.camera_id}] 采集进程已启动 ({width}x{height})")

    max_delay = 60
    base_delay = 1
    reconnect_attempts = 0

    while not stop_event.is_set():
        ret, frame = cap.read()
        if not ret:
            cap.release()
            reconnect_attempts += 1
            delay = min(base_delay * (2 ** (reconnect_attempts - 1)), max_delay)
            print(f"[CAM {self.camera_id}] 读取失败，{delay}s 后重连 (第 {reconnect_attempts} 次)")
            time.sleep(delay)
            # 重连
            cap = cv2.VideoCapture(source) if is_rtsp else cv2.VideoCapture(int(source), cv2.CAP_DSHOW)
            if cap.isOpened():
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
                reconnect_attempts = 0
            continue

        reconnect_attempts = 0
        # 缩放到目标尺寸并写入共享内存
        if frame.shape[:2] != (height, width):
            frame = cv2.resize(frame, (width, height))
        np.copyto(shared_frame, frame)

        time.sleep(0.01)  # ~100fps 上限

    cap.release()
    shm.close()
    print(f"[CAM {self.camera_id}] 采集进程已停止")
