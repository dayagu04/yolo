"""
数据库模块 - SQLAlchemy ORM
提供告警记录的持久化存储
"""
from sqlalchemy import (
    create_engine, Column, Integer, String, DateTime, Text, Enum, JSON, TIMESTAMP, text, func
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import QueuePool
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict
from contextlib import contextmanager
import logging

Base = declarative_base()


class Alert(Base):
    """告警记录表"""
    __tablename__ = "alerts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime(timezone=True), nullable=False, index=True)
    camera_id = Column(Integer, nullable=False, index=True)
    person_count = Column(Integer, nullable=False)
    new_track_ids = Column(JSON)
    screenshot_path = Column(String(512))
    message = Column(String(512))
    level = Column(Enum("low", "medium", "high"), default="high", index=True)
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
        }


class Camera(Base):
    """摄像头配置表"""
    __tablename__ = "cameras"

    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    location = Column(String(200))
    status = Column(Enum("online", "offline", "error"), default="offline")
    last_seen = Column(DateTime)
    resolution = Column(String(20))
    created_at = Column(TIMESTAMP, default=lambda: datetime.now(timezone.utc))


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
        except Exception:
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

