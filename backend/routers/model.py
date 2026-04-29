"""模型管理路由"""
from fastapi import APIRouter, HTTPException, Request, Depends, Query
from typing import Optional
from backend.auth import get_current_user, require_admin
from backend.routers.deps import get_cameras, audit

model_router = APIRouter(prefix="/api/v1", tags=["模型"])


@model_router.post("/model/reload")
async def reload_model(
    request: Request,
    camera_id: Optional[int] = Query(None),
    model_path: Optional[str] = Query(None),
    _user: dict = Depends(require_admin),
):
    cameras = get_cameras(request)
    results = {}
    target = {camera_id: cameras[camera_id]} if camera_id and camera_id in cameras else cameras
    for cid, cam in target.items():
        success = cam.reload_model(model_path)
        results[cid] = "ok" if success else "failed"
    audit(request, _user["sub"], "model_reload", resource=f"camera:{camera_id or 'all'}",
          detail=f"path={model_path or 'default'}, results={results}")
    return {"results": results}


@model_router.get("/model/info")
async def model_info(request: Request, _user: dict = Depends(get_current_user)):
    from pathlib import Path
    from backend.main import ROOT
    cameras = get_cameras(request)
    model_file = ROOT / "models" / "person_best.pt"
    info = {
        "model_path": str(model_file),
        "exists": model_file.exists(),
        "size_mb": round(model_file.stat().st_size / 1024 / 1024, 1) if model_file.exists() else None,
        "loaded_in_cameras": {cid: cam._model is not None for cid, cam in cameras.items()},
    }
    return info


@model_router.get("/models")
async def list_models(_user: dict = Depends(get_current_user)):
    from backend.model_manager import model_manager
    return {"loaded": model_manager.list_models(), "available": model_manager.scan_available()}


@model_router.post("/models/{name}/load")
async def load_model(name: str, request: Request, _user: dict = Depends(require_admin)):
    from backend.model_manager import model_manager
    try:
        body = await request.json()
    except Exception:
        body = {}
    path = body.get("path", f"models/{name}.pt")
    device = body.get("device", "cpu")
    success = model_manager.load_model(name, path, device)
    if not success:
        raise HTTPException(status_code=500, detail=f"模型 '{name}' 加载失败")
    audit(request, _user["sub"], "model_load", resource=name, detail=f"path={path}, device={device}")
    return {"status": "ok", "models": model_manager.list_models()}


@model_router.post("/models/{name}/unload")
async def unload_model(name: str, request: Request, _user: dict = Depends(require_admin)):
    from backend.model_manager import model_manager
    success = model_manager.unload_model(name)
    if not success:
        raise HTTPException(status_code=404, detail=f"模型 '{name}' 未加载")
    audit(request, _user["sub"], "model_unload", resource=name)
    return {"status": "ok", "models": model_manager.list_models()}
