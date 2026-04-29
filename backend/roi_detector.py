"""
ROI（感兴趣区域）检测模块
支持区域入侵、徘徊检测、聚集检测
"""
import time
import logging
from typing import Optional
from collections import defaultdict
import numpy as np


class ROIDetector:
    """ROI 区域检测器"""

    def __init__(self, db_manager=None):
        self.db_manager = db_manager
        self.logger = logging.getLogger(__name__)
        self._rois: dict[int, list[dict]] = {}  # camera_id -> roi list
        self._person_tracks: dict[str, dict] = {}  # track_id -> {positions, timestamps}
        self._last_load_ts: float = 0
        self._load_interval: float = 30.0  # 每 30 秒重新加载 ROI 配置

    def _ensure_rois_loaded(self, camera_id: int):
        """确保 ROI 配置已加载"""
        now = time.time()
        if now - self._last_load_ts > self._load_interval:
            self._reload_rois()

    def _reload_rois(self):
        """从数据库重新加载所有 ROI 配置"""
        if not self.db_manager:
            return
        try:
            all_rois = self.db_manager.get_rois()
            self._rois.clear()
            for roi in all_rois:
                cam_id = roi["camera_id"]
                if cam_id not in self._rois:
                    self._rois[cam_id] = []
                self._rois[cam_id].append(roi)
            self._last_load_ts = time.time()
        except Exception as e:
            self.logger.error(f"加载 ROI 配置失败: {e}")

    def check_intrusion(
        self, camera_id: int, bbox_list: list[tuple], track_ids: list[int]
    ) -> list[dict]:
        """
        检测区域入侵
        Args:
            camera_id: 摄像头 ID
            bbox_list: 边界框列表 [(x1, y1, x2, y2), ...]
            track_ids: 对应的跟踪 ID
        Returns:
            触发的告警列表
        """
        self._ensure_rois_loaded(camera_id)
        rois = self._rois.get(camera_id, [])
        if not rois:
            return []

        alerts = []
        for roi in rois:
            if roi["roi_type"] != "intrusion" or not roi["enabled"]:
                continue

            polygon = np.array(roi["polygon"], dtype=np.int32)
            intruders = []

            for i, (bbox, track_id) in enumerate(zip(bbox_list, track_ids)):
                # 使用边界框底部中心点作为人员位置
                cx = (bbox[0] + bbox[2]) / 2
                cy = bbox[3]  # 底部
                if self._point_in_polygon(cx, cy, polygon):
                    intruders.append(track_id)

            if len(intruders) >= roi["min_persons"]:
                alerts.append({
                    "roi_id": roi["id"],
                    "roi_name": roi["name"],
                    "roi_type": "intrusion",
                    "camera_id": camera_id,
                    "person_count": len(intruders),
                    "track_ids": intruders,
                    "alert_level": roi["alert_level"],
                    "message": f"区域 '{roi['name']}' 检测到 {len(intruders)} 人入侵",
                })

        return alerts

    def check_loitering(
        self, camera_id: int, bbox_list: list[tuple], track_ids: list[int]
    ) -> list[dict]:
        """
        检测徘徊行为（人员在区域内停留过久）
        """
        self._ensure_rois_loaded(camera_id)
        rois = self._rois.get(camera_id, [])
        if not rois:
            return []

        now = time.time()
        alerts = []

        for roi in rois:
            if roi["roi_type"] != "loitering" or not roi["enabled"]:
                continue

            polygon = np.array(roi["polygon"], dtype=np.int32)
            min_duration = roi.get("min_duration_sec", 60)

            for bbox, track_id in zip(bbox_list, track_ids):
                cx = (bbox[0] + bbox[2]) / 2
                cy = bbox[3]
                in_polygon = self._point_in_polygon(cx, cy, polygon)

                track_key = f"{camera_id}_{track_id}"
                if track_key not in self._person_tracks:
                    self._person_tracks[track_key] = {
                        "positions": [],
                        "timestamps": [],
                        "in_roi_since": None,
                    }

                track = self._person_tracks[track_key]
                track["positions"].append((cx, cy))
                track["timestamps"].append(now)

                # 清理过期数据（保留最近 5 分钟）
                cutoff = now - 300
                while track["timestamps"] and track["timestamps"][0] < cutoff:
                    track["timestamps"].pop(0)
                    track["positions"].pop(0)

                if in_polygon:
                    if track["in_roi_since"] is None:
                        track["in_roi_since"] = now
                    elif now - track["in_roi_since"] >= min_duration:
                        alerts.append({
                            "roi_id": roi["id"],
                            "roi_name": roi["name"],
                            "roi_type": "loitering",
                            "camera_id": camera_id,
                            "person_count": 1,
                            "track_ids": [track_id],
                            "alert_level": roi["alert_level"],
                            "duration_sec": int(now - track["in_roi_since"]),
                            "message": f"区域 '{roi['name']}' 检测到徘徊行为（停留 {int(now - track['in_roi_since'])}s）",
                        })
                else:
                    track["in_roi_since"] = None

        return alerts

    def check_gathering(
        self, camera_id: int, bbox_list: list[tuple], track_ids: list[int]
    ) -> list[dict]:
        """
        检测聚集行为（多人聚集在同一区域）
        """
        self._ensure_rois_loaded(camera_id)
        rois = self._rois.get(camera_id, [])
        if not rois:
            return []

        alerts = []
        for roi in rois:
            if roi["roi_type"] != "gathering" or not roi["enabled"]:
                continue

            polygon = np.array(roi["polygon"], dtype=np.int32)
            min_persons = roi.get("min_persons", 3)

            persons_in_roi = []
            for bbox, track_id in zip(bbox_list, track_ids):
                cx = (bbox[0] + bbox[2]) / 2
                cy = bbox[3]
                if self._point_in_polygon(cx, cy, polygon):
                    persons_in_roi.append(track_id)

            if len(persons_in_roi) >= min_persons:
                alerts.append({
                    "roi_id": roi["id"],
                    "roi_name": roi["name"],
                    "roi_type": "gathering",
                    "camera_id": camera_id,
                    "person_count": len(persons_in_roi),
                    "track_ids": persons_in_roi,
                    "alert_level": roi["alert_level"],
                    "message": f"区域 '{roi['name']}' 检测到 {len(persons_in_roi)} 人聚集",
                })

        return alerts

    def check_all(
        self, camera_id: int, bbox_list: list[tuple], track_ids: list[int]
    ) -> list[dict]:
        """执行所有启用的 ROI 检测"""
        alerts = []
        alerts.extend(self.check_intrusion(camera_id, bbox_list, track_ids))
        alerts.extend(self.check_loitering(camera_id, bbox_list, track_ids))
        alerts.extend(self.check_gathering(camera_id, bbox_list, track_ids))
        return alerts

    @staticmethod
    def _point_in_polygon(x: float, y: float, polygon: np.ndarray) -> bool:
        """判断点是否在多边形内部（射线法）"""
        n = len(polygon)
        inside = False
        j = n - 1
        for i in range(n):
            xi, yi = polygon[i]
            xj, yj = polygon[j]
            if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi) + xi):
                inside = not inside
            j = i
        return inside

    def cleanup_stale_tracks(self, max_age_sec: int = 300):
        """清理过期的跟踪记录"""
        now = time.time()
        stale_keys = [
            k for k, v in self._person_tracks.items()
            if v["timestamps"] and now - v["timestamps"][-1] > max_age_sec
        ]
        for k in stale_keys:
            del self._person_tracks[k]
