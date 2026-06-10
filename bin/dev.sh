#!/bin/bash
# YOLO 安防监控系统开发模式启动脚本 (热重载)

set -e

cd "$(dirname "$0")/.."

# 加载环境变量
if [ -f .env ]; then
    echo "[INFO] Loading environment variables from .env"
    export $(cat .env | grep -v '^#' | grep -v '^$' | xargs)
else
    echo "[WARNING] .env file not found, using defaults"
fi

echo "Starting YOLO Security Monitor in DEVELOPMENT mode..."
echo "Hot reload is ENABLED - code changes will restart the server"
echo "Access the application at: http://localhost:8000"
echo ""

uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
