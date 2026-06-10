@echo off
REM YOLO 安防监控系统启动脚本 (Windows)

cd /d %~dp0\..

REM 从 .env 文件加载环境变量
if exist .env (
    echo [INFO] Loading environment variables from .env
    for /f "usebackq tokens=1,* delims==" %%a in (".env") do (
        if not "%%a"=="" if not "%%a:~0,1%"=="#" set "%%a=%%b"
    )
) else (
    echo [ERROR] .env file not found. Please copy .env.example to .env and configure it.
    exit /b 1
)

echo Starting YOLO Security Monitor on port 8000...
echo Access the application at: http://localhost:8000
echo.

uvicorn backend.main:app --host 0.0.0.0 --port 8000
