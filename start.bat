@echo off
cd /d %~dp0

REM 从 .env 文件加载环境变量
if exist .env (
    for /f "usebackq tokens=1,* delims==" %%a in (".env") do (
        set "%%a=%%b"
    )
) else (
    echo [ERROR] .env file not found. Copy .env.example to .env and fill in your secrets.
    exit /b 1
)

echo Starting YOLO Security Monitor on port 9000...
uvicorn backend.main:app --host 0.0.0.0 --port 9000
