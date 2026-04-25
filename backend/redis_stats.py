"""
Redis 实时统计模块
提供实时统计数据，减少 MySQL 查询压力
"""
import redis
from typing import Optional, Dict, List
from datetime import datetime, timedelta
import logging


class RedisStats:
    """Redis 实时统计管理器"""

    def __init__(self, config: dict):
        """
        初始化 Redis 连接
        Args:
            config: Redis 配置字典
        """
        self.config = config
        self.logger = logging.getLogger(__name__)
        self.enabled = config.get("enabled", False)

        if not self.enabled:
            self.logger.info("Redis 统计功能未启用")
            self.client = None
            return

        try:
            self.client = redis.Redis(
                host=config.get("host", "localhost"),
                port=config.get("port", 6379),
                password=config.get("password") or None,
                db=config.get("db", 0),
                decode_responses=config.get("decode_responses", True),
                socket_connect_timeout=5,
            )
            # 测试连接
            self.client.ping()
            self.logger.info("Redis 连接成功")
        except Exception as e:
            self.logger.error(f"Redis 连接失败: {e}")
            self.enabled = False
            self.client = None

    def is_enabled(self) -> bool:
        """检查 Redis 是否可用"""
        return self.enabled and self.client is not None

    # ------------------------------------------------------------------ #
    #  告警统计
    # ------------------------------------------------------------------ #

    def incr_today_alerts(self, camera_id: Optional[int] = None):
        """增加今日告警计数"""
        if not self.is_enabled():
            return

        try:
            # 今日总告警数
            self.client.incr("stats:today:alerts")

            # 各摄像头今日告警数
            if camera_id is not None:
                self.client.incr(f"stats:today:cam:{camera_id}")

            # 每小时告警数（Sorted Set）
            now = datetime.now()
            date_key = now.strftime("%Y-%m-%d")
            hour = now.hour
            self.client.zincrby(f"stats:hourly:{date_key}", 1, str(hour))

            # 设置过期时间（次日凌晨 3 点过期，TTL 27 小时）
            expire_at = (now + timedelta(days=1)).replace(
                hour=3, minute=0, second=0, microsecond=0
            )
            ttl = int((expire_at - now).total_seconds())

            self.client.expire("stats:today:alerts", ttl)
            if camera_id is not None:
                self.client.expire(f"stats:today:cam:{camera_id}", ttl)
            self.client.expire(f"stats:hourly:{date_key}", ttl)

        except Exception as e:
            self.logger.error(f"Redis 增加告警计数失败: {e}")

    def get_today_alerts(self) -> int:
        """获取今日总告警数"""
        if not self.is_enabled():
            return 0
        try:
            count = self.client.get("stats:today:alerts")
            return int(count) if count else 0
        except Exception as e:
            self.logger.error(f"Redis 获取今日告警数失败: {e}")
            return 0

    def get_camera_alerts(self, camera_id: int) -> int:
        """获取指定摄像头今日告警数"""
        if not self.is_enabled():
            return 0
        try:
            count = self.client.get(f"stats:today:cam:{camera_id}")
            return int(count) if count else 0
        except Exception as e:
            self.logger.error(f"Redis 获取摄像头告警数失败: {e}")
            return 0

    def get_all_camera_alerts(self) -> Dict[str, int]:
        """获取所有摄像头今日告警数"""
        if not self.is_enabled():
            return {}
        try:
            keys = self.client.keys("stats:today:cam:*")
            result = {}
            for key in keys:
                camera_id = key.split(":")[-1]
                count = self.client.get(key)
                result[camera_id] = int(count) if count else 0
            return result
        except Exception as e:
            self.logger.error(f"Redis 获取所有摄像头告警数失败: {e}")
            return {}

    def get_hourly_alerts(self, date: Optional[str] = None) -> Dict[str, int]:
        """
        获取每小时告警数
        Args:
            date: 日期字符串 (YYYY-MM-DD)，默认今天
        Returns:
            {"0": 5, "1": 2, "8": 15, ...}
        """
        if not self.is_enabled():
            return {}
        try:
            if date is None:
                date = datetime.now().strftime("%Y-%m-%d")

            data = self.client.zrange(
                f"stats:hourly:{date}", 0, -1, withscores=True
            )
            return {hour: int(count) for hour, count in data}
        except Exception as e:
            self.logger.error(f"Redis 获取每小时告警数失败: {e}")
            return {}

    # ------------------------------------------------------------------ #
    #  摄像头状态
    # ------------------------------------------------------------------ #

    def set_camera_online(self, camera_id: int):
        """标记摄像头在线"""
        if not self.is_enabled():
            return
        try:
            self.client.sadd("stats:online:cameras", camera_id)
        except Exception as e:
            self.logger.error(f"Redis 标记摄像头在线失败: {e}")

    def set_camera_offline(self, camera_id: int):
        """标记摄像头离线"""
        if not self.is_enabled():
            return
        try:
            self.client.srem("stats:online:cameras", camera_id)
        except Exception as e:
            self.logger.error(f"Redis 标记摄像头离线失败: {e}")

    def get_online_cameras(self) -> List[int]:
        """获取在线摄像头列表"""
        if not self.is_enabled():
            return []
        try:
            cameras = self.client.smembers("stats:online:cameras")
            return [int(c) for c in cameras]
        except Exception as e:
            self.logger.error(f"Redis 获取在线摄像头失败: {e}")
            return []

    # ------------------------------------------------------------------ #
    #  当前人数
    # ------------------------------------------------------------------ #

    def update_current_persons(self, camera_id: int, count: int):
        """更新当前摄像头人数"""
        if not self.is_enabled():
            return
        try:
            self.client.hset("stats:current:persons", camera_id, count)
        except Exception as e:
            self.logger.error(f"Redis 更新当前人数失败: {e}")

    def get_current_persons(self, camera_id: Optional[int] = None) -> Dict[str, int]:
        """
        获取当前人数
        Args:
            camera_id: 指定摄像头 ID，None 表示获取所有
        Returns:
            {"0": 3, "1": 0, "2": 5}
        """
        if not self.is_enabled():
            return {}
        try:
            if camera_id is not None:
                count = self.client.hget("stats:current:persons", camera_id)
                return {str(camera_id): int(count) if count else 0}
            else:
                data = self.client.hgetall("stats:current:persons")
                return {k: int(v) for k, v in data.items()}
        except Exception as e:
            self.logger.error(f"Redis 获取当前人数失败: {e}")
            return {}

    # ------------------------------------------------------------------ #
    #  综合统计
    # ------------------------------------------------------------------ #

    def get_all_stats(self) -> Dict:
        """获取所有统计数据"""
        return {
            "today_alerts": self.get_today_alerts(),
            "online_cameras": self.get_online_cameras(),
            "current_persons": self.get_current_persons(),
            "hourly_alerts": self.get_hourly_alerts(),
            "camera_alerts": self.get_all_camera_alerts(),
        }

    def reset_daily_stats(self):
        """重置每日统计（凌晨定时任务调用）"""
        if not self.is_enabled():
            return
        try:
            # 删除今日统计
            self.client.delete("stats:today:alerts")
            keys = self.client.keys("stats:today:cam:*")
            if keys:
                self.client.delete(*keys)

            # 删除昨天的小时统计
            yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
            self.client.delete(f"stats:hourly:{yesterday}")

            self.logger.info("每日统计已重置")
        except Exception as e:
            self.logger.error(f"Redis 重置每日统计失败: {e}")
