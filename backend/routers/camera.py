"""摄像头管理路由"""
from fastapi import APIRouter, HTTPException, Request, Depends, Query
from backend.auth import get_current_user, require_operator, require_admin
from backend.schemas import DetectionConfig
from backend.routers.deps import get_db, get_config, get_cameras, get_redis, get_logger, get_event_loop, audit

camera_router = APIRouter(prefix="/api/v1", tags=["摄像头"])


def _get_or_create_camera(camera_id: int, cam_cfg: dict = None):
    """获取或创建摄像头实例（延迟导入避免循环）"""
    from backend.main import get_camera
    return get_camera(camera_id, cam_cfg)


@camera_router.get("/cameras")
async def list_cameras(request: Request, _user: dict = Depends(get_current_user)):
    config = get_config(request)
    cameras = get_cameras(request)
    cameras_cfg = config.get("cameras", [])
    result = []
    for cam_cfg in cameras_cfg:
        cam_id = cam_cfg["id"]
        cam = cameras.get(cam_id)
        item = {
            "id": cam_id,
            "name": cam_cfg.get("name", f"Camera {cam_id}"),
            "location": cam_cfg.get("location", ""),
            "source": str(cam_cfg.get("source", cam_id)),
        }
        if cam:
            item.update(cam.get_status())
            item["id"] = cam_id
        else:
            item.update({"connected": False, "running": False, "model_loaded": False})
        result.append(item)
    return {"cameras": result, "total": len(result)}


@camera_router.post("/cameras/{camera_id}/config")
async def update_config(
    camera_id: int, cfg: DetectionConfig, request: Request,
    _user: dict = Depends(require_operator),
):
    camera = _get_or_create_camera(camera_id)
    if cfg.enabled is not None:
        camera.toggle_detection(cfg.enabled)
    if cfg.conf is not None:
        camera.set_conf(cfg.conf)
    logger = get_logger(request)
    if logger:
        logger.log("info", "camera.config_updated", "摄像头配置已更新",
                    camera_id=camera_id, data={"enabled": cfg.enabled, "conf": cfg.conf})
    return camera.get_status()


@camera_router.get("/camera/{camera_id}/status")
async def camera_status(camera_id: int, _user: dict = Depends(get_current_user)):
    return _get_or_create_camera(camera_id).get_status()


@camera_router.post("/cameras/{camera_id}/add")
async def add_camera(camera_id: int, request: Request, _user: dict = Depends(require_operator)):
    cameras = get_cameras(request)
    if camera_id in cameras:
        raise HTTPException(status_code=409, detail=f"摄像头 {camera_id} 已存在")

    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=422, detail="请求体必须是合法的 JSON")

    source = body.get("source")
    if source is None:
        raise HTTPException(status_code=422, detail="source 字段必填")

    cam_cfg = {
        "id": camera_id,
        "source": source,
        "name": body.get("name", f"Camera {camera_id}"),
        "location": body.get("location", ""),
        "auto_resolution": body.get("auto_resolution", True),
        "width": body.get("width", 1280),
        "height": body.get("height", 720),
    }

    try:
        cam = _get_or_create_camera(camera_id, cam_cfg)
        audit(request, _user["sub"], "camera_add", resource=f"camera:{camera_id}",
              detail=f"name={cam_cfg['name']}, source={source}")
        logger = get_logger(request)
        if logger:
            logger.log("info", "camera.added", f"摄像头 {camera_id} 已动态添加",
                        camera_id=camera_id, data={"name": cam_cfg["name"], "source": str(source)})
        return {
            "id": camera_id, "name": cam_cfg["name"],
            "location": cam_cfg["location"], "source": str(cam_cfg["source"]),
            **cam.get_status(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"添加摄像头失败: {e}")


@camera_router.post("/cameras/{camera_id}/remove")
async def remove_camera(camera_id: int, request: Request, _user: dict = Depends(require_admin)):
    cameras = get_cameras(request)
    if camera_id not in cameras:
        raise HTTPException(status_code=404, detail=f"摄像头 {camera_id} 不存在")

    cam = cameras.pop(camera_id)
    try:
        cam.stop()
        redis = get_redis(request)
        if redis and redis.is_enabled():
            redis.set_camera_offline(camera_id)
    except Exception as e:
        logger = get_logger(request)
        if logger:
            logger.log("warning", "camera.stop_failed", f"停止摄像头 {camera_id} 失败: {e}")

    audit(request, _user["sub"], "camera_remove", resource=f"camera:{camera_id}")
    logger = get_logger(request)
    if logger:
        logger.log("info", "camera.removed", f"摄像头 {camera_id} 已移除", camera_id=camera_id)
    return {"success": True, "camera_id": camera_id}


@camera_router.put("/cameras/{camera_id}")
async def edit_camera(camera_id: int, request: Request, _user: dict = Depends(require_operator)):
    """编辑摄像头配置（名称/位置）"""
    cameras = get_cameras(request)
    config = get_config(request)
    if camera_id not in cameras:
        raise HTTPException(status_code=404, detail=f"摄像头 {camera_id} 不存在")

    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=422, detail="请求体必须是合法的 JSON")

    # 更新配置文件中的摄像头信息
    cameras_cfg = config.get("cameras", [])
    for cam_cfg in cameras_cfg:
        if cam_cfg["id"] == camera_id:
            if "name" in body:
                cam_cfg["name"] = body["name"]
            if "location" in body:
                cam_cfg["location"] = body["location"]
            break

    audit(request, _user["sub"], "camera_edit", resource=f"camera:{camera_id}",
          detail=str(body))
    return {"status": "ok", "camera_id": camera_id}
