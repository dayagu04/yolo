"""
消息协议定义 - 所有 WebSocket 与 API 消息的 Schema
"""
from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, Literal, Any
from datetime import datetime


# ------------------------------------------------------------------ #
#  WebSocket 消息协议
# ------------------------------------------------------------------ #

class AlertMessage(BaseModel):
    """告警事件消息"""
    type: Literal["alert"] = "alert"
    timestamp: str = Field(description="ISO 8601 格式时间戳")
    level: Literal["low", "medium", "high"] = "high"
    message: str
    camera_id: int
    data: dict = Field(default_factory=dict)


class StatusMessage(BaseModel):
    """状态事件消息"""
    type: Literal["status"] = "status"
    timestamp: str
    level: Literal["info", "warning", "error"] = "info"
    message: str
    camera_id: int
    data: dict = Field(default_factory=dict)


class LogMessage(BaseModel):
    """日志事件消息"""
    type: Literal["log"] = "log"
    timestamp: str
    level: Literal["debug", "info", "warning", "error"] = "info"
    message: str
    camera_id: Optional[int] = None
    event: str = Field(description="事件标识符，如 camera.read_failed")
    data: dict = Field(default_factory=dict)


# ------------------------------------------------------------------ #
#  API 请求/响应
# ------------------------------------------------------------------ #

class DetectionConfig(BaseModel):
    """检测配置"""
    enabled: Optional[bool] = None
    conf: Optional[float] = Field(None, ge=0.1, le=0.95)


class LoginRequest(BaseModel):
    """登录请求"""
    username: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=1)


class TokenResponse(BaseModel):
    """登录成功响应"""
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    role: str


class UserInfo(BaseModel):
    """当前用户信息"""
    username: str
    role: str


class CameraStatus(BaseModel):
    """摄像头状态"""
    model_config = ConfigDict(protected_namespaces=())

    camera_id: int
    running: bool
    connected: bool
    model_loaded: bool
    detection_enabled: bool
    conf_threshold: float
    fps: float = 0.0
    last_frame_age_ms: float = 0.0
    reconnect_attempts: int = 0


class HealthResponse(BaseModel):
    """健康检查响应"""
    status: Literal["ok", "degraded", "error"]
    uptime_sec: float
    ws_clients: int
    camera_count: int
    cameras: list[CameraStatus]


class LogEntry(BaseModel):
    """日志条目"""
    timestamp: str
    level: str
    event: str
    camera_id: Optional[int]
    message: str
    data: dict = Field(default_factory=dict)
