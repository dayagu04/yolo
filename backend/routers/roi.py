"""ROI 配置路由"""
from fastapi import APIRouter, HTTPException, Request, Depends, Query
from typing import Optional
from backend.auth import get_current_user, require_operator
from backend.routers.deps import get_db, audit

roi_router = APIRouter(prefix="/api/v1/rois", tags=["ROI"])


@roi_router.get("")
async def list_rois(request: Request, camera_id: Optional[int] = Query(None), _user: dict = Depends(get_current_user)):
    db = get_db(request)
    return db.get_rois(camera_id)


@roi_router.post("")
async def create_roi(request: Request, _user: dict = Depends(require_operator)):
    db = get_db(request)
    body = await request.json()
    required = ["camera_id", "name", "polygon"]
    for field in required:
        if field not in body:
            raise HTTPException(status_code=422, detail=f"{field} 必填")
    roi = db.create_roi(
        camera_id=body["camera_id"], name=body["name"],
        roi_type=body.get("roi_type", "intrusion"), polygon=body["polygon"],
        min_persons=body.get("min_persons", 1),
        min_duration_sec=body.get("min_duration_sec", 0),
        alert_level=body.get("alert_level", "high"),
    )
    audit(request, _user["sub"], "roi_create", resource=f"camera:{body['camera_id']}",
          detail=f"ROI: {body['name']}")
    return roi


@roi_router.put("/{roi_id}")
async def update_roi(roi_id: int, request: Request, _user: dict = Depends(require_operator)):
    db = get_db(request)
    body = await request.json()
    success = db.update_roi(roi_id, **body)
    if not success:
        raise HTTPException(status_code=404, detail="ROI 不存在")
    audit(request, _user["sub"], "roi_update", resource=f"roi:{roi_id}")
    return {"status": "ok"}


@roi_router.delete("/{roi_id}")
async def delete_roi(roi_id: int, request: Request, _user: dict = Depends(require_operator)):
    db = get_db(request)
    success = db.delete_roi(roi_id)
    if not success:
        raise HTTPException(status_code=404, detail="ROI 不存在")
    audit(request, _user["sub"], "roi_delete", resource=f"roi:{roi_id}")
    return {"status": "ok"}
