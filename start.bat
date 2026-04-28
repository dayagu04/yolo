@echo off
cd /d %~dp0
set YOLO_DATABASE_PASSWORD=Rudai2003
set YOLO_AUTH_SECRET_KEY=a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0u1v2w3x4y5z6
set YOLO_AUTH_INIT_ADMIN_PASSWORD=gudaya040214
echo Starting YOLO Security Monitor on port 9000...
uvicorn backend.main:app --host 0.0.0.0 --port 9000
