from backend.routers.auth import auth_router
from backend.routers.camera import camera_router
from backend.routers.alert import alert_router
from backend.routers.roi import roi_router
from backend.routers.model import model_router
from backend.routers.system import system_router

__all__ = ["auth_router", "camera_router", "alert_router", "roi_router", "model_router", "system_router"]
