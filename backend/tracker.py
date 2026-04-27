"""
人员轨迹管理器 - IoU + 中心点双重匹配
"""


class PersonTracker:
    """轻量级人员轨迹管理，负责检测框关联与告警去重"""

    def __init__(self, track_ttl_sec: float = 2.0, alert_cooldown_sec: float = 5.0):
        self.track_ttl_sec = track_ttl_sec
        self.alert_cooldown_sec = alert_cooldown_sec
        self._next_track_id = 1
        self._tracks: dict[int, dict] = {}
        self._last_alert_time = 0.0

    @staticmethod
    def _iou(a: tuple, b: tuple) -> float:
        ax1, ay1, ax2, ay2 = a
        bx1, by1, bx2, by2 = b
        ix1, iy1 = max(ax1, bx1), max(ay1, by1)
        ix2, iy2 = min(ax2, bx2), min(ay2, by2)
        iw = max(0.0, ix2 - ix1)
        ih = max(0.0, iy2 - iy1)
        inter = iw * ih
        if inter <= 0:
            return 0.0
        area_a = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
        area_b = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
        union = area_a + area_b - inter
        return inter / union if union > 0 else 0.0

    def associate(self, boxes: list[tuple], now_ts: float) -> list[int]:
        """将检测框与已有轨迹关联，返回活跃 track_id 列表"""
        matched: set[int] = set()
        active_ids: list[int] = []

        for box in boxes:
            bx_c = (box[0] + box[2]) / 2
            by_c = (box[1] + box[3]) / 2
            best_id, best_score = None, -1.0

            for tid, track in self._tracks.items():
                if tid in matched:
                    continue
                iou = self._iou(box, track["bbox"])
                tc = track["center"]
                dist = ((bx_c - tc[0]) ** 2 + (by_c - tc[1]) ** 2) ** 0.5
                # 优先 IoU，IoU 为 0 时用距离倒数作为备用分数
                if iou > 0.3:
                    score = iou
                elif dist < 50.0:
                    score = dist / -100.0  # 负值，低于任何 IoU 匹配，但高于 -1
                else:
                    continue
                if score > best_score:
                    best_score = score
                    best_id = tid

            if best_id is None:
                tid = self._next_track_id
                self._next_track_id += 1
                self._tracks[tid] = {
                    "bbox": box,
                    "center": (bx_c, by_c),
                    "last_seen": now_ts,
                    "alerted": False,
                }
                active_ids.append(tid)
                matched.add(tid)
            else:
                self._tracks[best_id].update({
                    "bbox": box,
                    "center": (bx_c, by_c),
                    "last_seen": now_ts,
                })
                active_ids.append(best_id)
                matched.add(best_id)

        expired = [
            tid for tid, t in self._tracks.items()
            if now_ts - t["last_seen"] > self.track_ttl_sec
        ]
        for tid in expired:
            self._tracks.pop(tid, None)

        return active_ids

    def get_pending_tracks(self, active_ids: list[int], now_ts: float) -> list[int]:
        """返回需要告警的新轨迹（通过冷却检查后返回）"""
        pending = [tid for tid in active_ids
                   if not self._tracks.get(tid, {}).get("alerted")]
        if not pending:
            return []
        if now_ts - self._last_alert_time < self.alert_cooldown_sec:
            return []
        return pending

    def mark_alerted(self, track_ids: list[int], now_ts: float):
        """标记轨迹已告警，更新冷却时间戳"""
        self._last_alert_time = now_ts
        for tid in track_ids:
            if tid in self._tracks:
                self._tracks[tid]["alerted"] = True

    @property
    def active_count(self) -> int:
        return len(self._tracks)
