"""
数据库模块 - SQLAlchemy ORM
提供告警记录的持久化存储
"""
from sqlalchemy import (
    create_engine, Column, Integer, String, DateTime, Text, Enum, JSON, TIMESTAMP, Boolean, text, ForeignKey, Index
)
from sqlalchemy.orm import sessionmaker, Session, DeclarativeBase
from sqlalchemy.pool import QueuePool
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict
from contextlib import contextmanager
import logging

class Base(DeclarativeBase):
    pass


class Alert(Base):
    """告警记录表"""
    __tablename__ = "alerts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime(timezone=True), nullable=False, index=True)
    camera_id = Column(Integer, ForeignKey("cameras.id", ondelete="SET NULL"), nullable=True, index=True)
    person_count = Column(Integer, nullable=False)
    new_track_ids = Column(JSON)
    screenshot_path = Column(String(512))
    message = Column(String(512))
    level = Column(Enum("low", "medium", "high"), default="high", index=True)
    acknowledged = Column(Boolean, default=False)
    acknowledged_by = Column(String(50))
    acknowledged_at = Column(DateTime(timezone=True))
    created_at = Column(TIMESTAMP, default=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "camera_id": self.camera_id,
            "person_count": self.person_count,
            "new_track_ids": self.new_track_ids,
            "screenshot_path": self.screenshot_path,
            "message": self.message,
            "level": self.level,
            "acknowledged": self.acknowledged,
            "acknowledged_by": self.acknowledged_by,
            "acknowledged_at": self.acknowledged_at.isoformat() if self.acknowledged_at else None,
        }


class Camera(Base):
    """摄像头配置表"""
    __tablename__ = "cameras"

    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    location = Column(String(200))
    status = Column(Enum("online", "offline", "error"), default="offline", index=True)
    last_seen = Column(DateTime)
    resolution = Column(String(20))
    created_at = Column(TIMESTAMP, default=lambda: datetime.now(timezone.utc))


class User(Base):
    """用户表"""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    role = Column(Enum("admin", "operator", "viewer"), default="viewer", nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(TIMESTAMP, default=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict:
        return {"id": self.id, "username": self.username, "role": self.role, "is_active": self.is_active}


class AuditLog(Base):
    """操作审计日志表"""
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime(timezone=True), nullable=False, index=True)
    username = Column(String(50), nullable=False, index=True)
    action = Column(String(50), nullable=False, index=True)  # login, logout, config_change, camera_add, camera_remove, user_create, user_delete
    resource = Column(String(200))  # 操作对象描述
    detail = Column(Text)  # 操作详情 JSON
    ip_address = Column(String(45))  # 支持 IPv6
    user_agent = Column(String(500))
    created_at = Column(TIMESTAMP, default=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "username": self.username,
            "action": self.action,
            "resource": self.resource,
            "detail": self.detail,
            "ip_address": self.ip_address,
        }


class AlertEscalation(Base):
    """告警升级记录表"""
    __tablename__ = "alert_escalations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    alert_id = Column(Integer, ForeignKey("alerts.id", ondelete="CASCADE"), nullable=False, index=True)
    from_level = Column(String(20), nullable=False)  # 原始告警级别
    to_level = Column(String(20), nullable=False)     # 升级后级别
    reason = Column(String(500))                       # 升级原因
    escalated_at = Column(DateTime(timezone=True), nullable=False)
    notified = Column(Boolean, default=False, index=True)  # 是否已通知
    notified_at = Column(DateTime(timezone=True))      # 通知时间
    created_at = Column(TIMESTAMP, default=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "alert_id": self.alert_id,
            "from_level": self.from_level,
            "to_level": self.to_level,
            "reason": self.reason,
            "escalated_at": self.escalated_at.isoformat() if self.escalated_at else None,
            "notified": self.notified,
            "notified_at": self.notified_at.isoformat() if self.notified_at else None,
        }


class CameraROI(Base):
    """摄像头 ROI（感兴趣区域）配置表"""
    __tablename__ = "camera_rois"

    id = Column(Integer, primary_key=True, autoincrement=True)
    camera_id = Column(Integer, ForeignKey("cameras.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(100), nullable=False)          # 区域名称
    roi_type = Column(
        Enum("intrusion", "loitering", "gathering", "monitoring"),
        default="intrusion", nullable=False,
    )
    polygon = Column(JSON, nullable=False)               # 多边形顶点坐标 [[x,y], ...]
    min_persons = Column(Integer, default=1)             # 触发最小人数
    min_duration_sec = Column(Integer, default=0)        # 最小持续时间（徘徊检测用）
    alert_level = Column(Enum("low", "medium", "high"), default="high")
    enabled = Column(Boolean, default=True, index=True)
    created_at = Column(TIMESTAMP, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(TIMESTAMP, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "camera_id": self.camera_id,
            "name": self.name,
            "roi_type": self.roi_type,
            "polygon": self.polygon,
            "min_persons": self.min_persons,
            "min_duration_sec": self.min_duration_sec,
            "alert_level": self.alert_level,
            "enabled": self.enabled,
        }


class DatabaseManager:
    """数据库管理器"""

    def __init__(self, config: dict):
        """
        初始化数据库连接
        Args:
            config: 数据库配置字典，包含 host, port, user, password, database 等
        """
        self.config = config
        self.logger = logging.getLogger(__name__)

        # 构建连接 URL
        db_url = (
            f"mysql+pymysql://{config['user']}:{config['password']}"
            f"@{config['host']}:{config['port']}/{config['database']}"
            f"?charset={config.get('charset', 'utf8mb4')}"
        )

        # 创建引擎（添加连接测试）
        try:
            self.engine = create_engine(
                db_url,
                poolclass=QueuePool,
                pool_size=config.get("pool_size", 5),
                pool_recycle=config.get("pool_recycle", 3600),
                echo=False,
                connect_args={"connect_timeout": 5}
            )

            # 测试连接
            with self.engine.connect() as conn:
                conn.execute(text("SELECT 1"))

            self.logger.info("数据库连接成功")
        except Exception as e:
            self.logger.error(f"数据库连接失败: {e}")
            raise

        # 创建会话工厂
        self.SessionLocal = sessionmaker(
            autocommit=False, autoflush=False, bind=self.engine
        )

    def create_tables(self):
        """创建所有表（如果不存在）"""
        Base.metadata.create_all(bind=self.engine)
        self.logger.info("数据库表初始化完成")

    def get_session(self) -> Session:
        return self.SessionLocal()

    @contextmanager
    def _session(self):
        """自动提交/回滚/关闭的会话上下文管理器"""
        session = self.SessionLocal()
        try:
            yield session
            session.commit()
        except Exception as e:
            session.rollback()
            raise
        finally:
            session.close()

    def create_alert(
        self,
        camera_id: int,
        person_count: int,
        new_track_ids: Optional[List[int]] = None,
        screenshot_path: Optional[str] = None,
        message: str = "",
        level: str = "high",
    ) -> int:
        with self._session() as session:
            alert = Alert(
                timestamp=datetime.now(),
                camera_id=camera_id,
                person_count=person_count,
                new_track_ids=new_track_ids or [],
                screenshot_path=screenshot_path,
                message=message,
                level=level,
            )
            session.add(alert)
            session.flush()
            alert_id = alert.id
            self.logger.info(f"告警已保存: ID={alert_id}, camera={camera_id}")
            return alert_id

    def query_alerts(
        self,
        limit: int = 50,
        offset: int = 0,
        camera_id: Optional[int] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        level: Optional[str] = None,
        order: str = "desc",
    ) -> Dict[str, any]:
        limit = max(1, min(500, limit))
        offset = max(0, offset)

        with self._session() as session:
            query = session.query(Alert)
            if camera_id is not None:
                query = query.filter(Alert.camera_id == camera_id)
            if start_time:
                query = query.filter(Alert.timestamp >= start_time)
            if end_time:
                query = query.filter(Alert.timestamp <= end_time)
            if level:
                query = query.filter(Alert.level == level)

            total = query.count()
            order_by = Alert.timestamp.desc() if order == "desc" else Alert.timestamp.asc()
            alerts = query.order_by(order_by).limit(limit).offset(offset).all()
            return {"total": total, "alerts": [a.to_dict() for a in alerts]}

    def get_alert_by_id(self, alert_id: int) -> Optional[dict]:
        with self._session() as session:
            alert = session.query(Alert).filter(Alert.id == alert_id).first()
            return alert.to_dict() if alert else None

    def acknowledge_alert(self, alert_id: int, username: str) -> bool:
        with self._session() as session:
            alert = session.query(Alert).filter(Alert.id == alert_id).first()
            if not alert or alert.acknowledged:
                return False
            alert.acknowledged = True
            alert.acknowledged_by = username
            alert.acknowledged_at = datetime.now()
            return True

    def delete_old_alerts(self, days: int = 30) -> int:
        with self._session() as session:
            cutoff = datetime.now() - timedelta(days=days)
            count = session.query(Alert).filter(Alert.timestamp < cutoff).delete()
            self.logger.info(f"已删除 {count} 条过期告警记录（{days} 天前）")
            return count

    def update_camera_status(
        self, camera_id: int, status: str, resolution: Optional[str] = None
    ):
        with self._session() as session:
            camera = session.query(Camera).filter(Camera.id == camera_id).first()
            if not camera:
                camera = Camera(id=camera_id, name=f"Camera {camera_id}")
                session.add(camera)
            camera.status = status
            camera.last_seen = datetime.now()
            if resolution:
                camera.resolution = resolution

    # ------------------------------------------------------------------ #
    #  用户 CRUD
    # ------------------------------------------------------------------ #

    def get_user_by_username(self, username: str) -> Optional[dict]:
        with self._session() as session:
            user = session.query(User).filter(User.username == username).first()
            return user.to_dict() | {"hashed_password": user.hashed_password} if user else None

    def create_user(self, username: str, hashed_password: str, role: str = "viewer") -> dict:
        with self._session() as session:
            user = User(username=username, hashed_password=hashed_password, role=role)
            session.add(user)
            session.flush()
            return user.to_dict()

    def user_exists(self) -> bool:
        """检查是否存在任意用户（用于首次启动初始化判断）。"""
        with self._session() as session:
            return session.query(User).count() > 0

    def list_users(self) -> list[dict]:
        with self._session() as session:
            users = session.query(User).order_by(User.id).all()
            return [u.to_dict() for u in users]

    def update_user(self, user_id: int, **kwargs) -> bool:
        with self._session() as session:
            user = session.query(User).filter(User.id == user_id).first()
            if not user:
                return False
            for k, v in kwargs.items():
                if hasattr(user, k) and k not in ("id", "created_at"):
                    setattr(user, k, v)
            return True

    def delete_user(self, user_id: int) -> bool:
        with self._session() as session:
            user = session.query(User).filter(User.id == user_id).first()
            if not user:
                return False
            session.delete(user)
            return True

    def update_password(self, user_id: int, hashed_password: str) -> bool:
        with self._session() as session:
            user = session.query(User).filter(User.id == user_id).first()
            if not user:
                return False
            user.hashed_password = hashed_password
            return True

    # ------------------------------------------------------------------ #
    #  审计日志 CRUD
    # ------------------------------------------------------------------ #

    def create_audit_log(
        self,
        username: str,
        action: str,
        resource: str = "",
        detail: str = "",
        ip_address: str = "",
        user_agent: str = "",
    ) -> int:
        with self._session() as session:
            log = AuditLog(
                timestamp=datetime.now(),
                username=username,
                action=action,
                resource=resource,
                detail=detail,
                ip_address=ip_address,
                user_agent=user_agent,
            )
            session.add(log)
            session.flush()
            return log.id

    def get_alert_stats(self, days: int = 7) -> Dict[str, any]:
        """获取告警统计：按天、按小时、按摄像头聚合"""
        from sqlalchemy import func, extract
        with self._session() as session:
            cutoff = datetime.now() - timedelta(days=days)

            # 按天聚合
            daily = session.query(
                func.date(Alert.timestamp).label("date"),
                func.count(Alert.id).label("count"),
            ).filter(Alert.timestamp >= cutoff).group_by(func.date(Alert.timestamp)).all()

            # 按小时聚合（最近 24 小时）
            h24_cutoff = datetime.now() - timedelta(hours=24)
            hourly = session.query(
                extract("hour", Alert.timestamp).label("hour"),
                func.count(Alert.id).label("count"),
            ).filter(Alert.timestamp >= h24_cutoff).group_by(extract("hour", Alert.timestamp)).all()

            # 按摄像头聚合
            by_camera = session.query(
                Alert.camera_id,
                func.count(Alert.id).label("count"),
            ).filter(Alert.timestamp >= cutoff).group_by(Alert.camera_id).all()

            # 按级别聚合
            by_level = session.query(
                Alert.level,
                func.count(Alert.id).label("count"),
            ).filter(Alert.timestamp >= cutoff).group_by(Alert.level).all()

            return {
                "period_days": days,
                "daily": {str(r.date): r.count for r in daily},
                "hourly": {int(r.hour): r.count for r in hourly},
                "by_camera": {int(r.camera_id): r.count for r in by_camera},
                "by_level": {r.level: r.count for r in by_level},
            }

    def get_person_trend(self, camera_id: Optional[int] = None, hours: int = 24) -> list[dict]:
        """获取人数趋势（基于告警记录中的 person_count）"""
        from sqlalchemy import func, extract
        with self._session() as session:
            cutoff = datetime.now() - timedelta(hours=hours)
            query = session.query(
                func.date(Alert.timestamp).label("date"),
                extract("hour", Alert.timestamp).label("hour"),
                Alert.camera_id,
                func.max(Alert.person_count).label("max_persons"),
                func.avg(Alert.person_count).label("avg_persons"),
            ).filter(Alert.timestamp >= cutoff)

            if camera_id is not None:
                query = query.filter(Alert.camera_id == camera_id)

            rows = query.group_by(
                func.date(Alert.timestamp), extract("hour", Alert.timestamp), Alert.camera_id
            ).all()

            return [
                {
                    "date": str(r.date),
                    "hour": int(r.hour),
                    "camera_id": int(r.camera_id),
                    "max_persons": int(r.max_persons),
                    "avg_persons": round(float(r.avg_persons), 1),
                }
                for r in rows
            ]

    def query_audit_logs(
        self,
        limit: int = 50,
        offset: int = 0,
        username: Optional[str] = None,
        action: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> Dict[str, any]:
        limit = max(1, min(500, limit))
        offset = max(0, offset)

        with self._session() as session:
            query = session.query(AuditLog)
            if username:
                query = query.filter(AuditLog.username == username)
            if action:
                query = query.filter(AuditLog.action == action)
            if start_time:
                query = query.filter(AuditLog.timestamp >= start_time)
            if end_time:
                query = query.filter(AuditLog.timestamp <= end_time)

            total = query.count()
            logs = query.order_by(AuditLog.timestamp.desc()).limit(limit).offset(offset).all()
            return {"total": total, "logs": [l.to_dict() for l in logs]}

    # ------------------------------------------------------------------ #
    #  告警升级 CRUD
    # ------------------------------------------------------------------ #

    def create_escalation(
        self,
        alert_id: int,
        from_level: str,
        to_level: str,
        reason: str = "",
    ) -> int:
        with self._session() as session:
            esc = AlertEscalation(
                alert_id=alert_id,
                from_level=from_level,
                to_level=to_level,
                reason=reason,
                escalated_at=datetime.now(),
            )
            session.add(esc)
            session.flush()
            return esc.id

    def get_pending_escalations(self, limit: int = 50) -> list[dict]:
        """获取未通知的升级记录"""
        with self._session() as session:
            rows = (
                session.query(AlertEscalation)
                .filter(AlertEscalation.notified == False)
                .order_by(AlertEscalation.escalated_at.asc())
                .limit(limit)
                .all()
            )
            return [r.to_dict() for r in rows]

    def mark_escalation_notified(self, escalation_id: int):
        with self._session() as session:
            esc = session.query(AlertEscalation).filter(AlertEscalation.id == escalation_id).first()
            if esc:
                esc.notified = True
                esc.notified_at = datetime.now()

    def escalate_alert(self, alert_id: int, new_level: str, reason: str = "") -> bool:
        """升级告警级别并记录升级历史"""
        with self._session() as session:
            alert = session.query(Alert).filter(Alert.id == alert_id).first()
            if not alert or alert.level == new_level:
                return False
            old_level = alert.level
            alert.level = new_level
            esc = AlertEscalation(
                alert_id=alert_id,
                from_level=old_level,
                to_level=new_level,
                reason=reason,
                escalated_at=datetime.now(),
            )
            session.add(esc)
            return True

    def get_alert_escalations(self, alert_id: int) -> list[dict]:
        """获取指定告警的升级历史"""
        with self._session() as session:
            rows = (
                session.query(AlertEscalation)
                .filter(AlertEscalation.alert_id == alert_id)
                .order_by(AlertEscalation.escalated_at.asc())
                .all()
            )
            return [r.to_dict() for r in rows]

    def get_unprocessed_alerts(self, older_than_sec: int = 300) -> list[dict]:
        """获取超过指定时间未处理的告警（用于升级调度）"""
        with self._session() as session:
            cutoff = datetime.now() - timedelta(seconds=older_than_sec)
            alerts = (
                session.query(Alert)
                .filter(Alert.timestamp <= cutoff, Alert.level != "high")
                .order_by(Alert.timestamp.asc())
                .all()
            )
            return [a.to_dict() for a in alerts]

    # ------------------------------------------------------------------ #
    #  ROI 配置 CRUD
    # ------------------------------------------------------------------ #

    def create_roi(self, camera_id: int, name: str, roi_type: str,
                   polygon: list, min_persons: int = 1,
                   min_duration_sec: int = 0, alert_level: str = "high") -> dict:
        with self._session() as session:
            roi = CameraROI(
                camera_id=camera_id, name=name, roi_type=roi_type,
                polygon=polygon, min_persons=min_persons,
                min_duration_sec=min_duration_sec, alert_level=alert_level,
            )
            session.add(roi)
            session.flush()
            return roi.to_dict()

    def get_rois(self, camera_id: Optional[int] = None) -> list[dict]:
        with self._session() as session:
            query = session.query(CameraROI).filter(CameraROI.enabled == True)
            if camera_id is not None:
                query = query.filter(CameraROI.camera_id == camera_id)
            return [r.to_dict() for r in query.all()]

    def update_roi(self, roi_id: int, **kwargs) -> bool:
        with self._session() as session:
            roi = session.query(CameraROI).filter(CameraROI.id == roi_id).first()
            if not roi:
                return False
            for k, v in kwargs.items():
                if hasattr(roi, k):
                    setattr(roi, k, v)
            return True

    def delete_roi(self, roi_id: int) -> bool:
        with self._session() as session:
            roi = session.query(CameraROI).filter(CameraROI.id == roi_id).first()
            if not roi:
                return False
            session.delete(roi)
            return True

