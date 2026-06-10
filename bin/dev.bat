@echo off
REM YOLO 安防监控系统开发模式启动脚本 (Windows)

cd /d %~dp0\..

REM 从 .env 文件加载环境变量
if exist .env (
    echo [INFO] Loading environment variables from .env
    for /f "usebackq tokens=1,* delims==" %%a in (".env") do (
        if not "%%a"=="" if not "%%a:~0,1%"=="#" set "%%a=%%b"
    )
) else (
    echo [WARNING] .env file not found, using defaults
)

echo Starting YOLO Security Monitor in DEVELOPMENT mode...
echo Hot reload is ENABLED - code changes will restart the server
echo Access the application at: http://localhost:8000
echo.

uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
