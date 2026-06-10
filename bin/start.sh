#!/bin/bash
# YOLO 安防监控系统启动脚本 (Linux/Mac)

set -e

cd "$(dirname "$0")/.."

# 加载环境变量
if [ -f .env ]; then
    echo "[INFO] Loading environment variables from .env"
    export $(cat .env | grep -v '^#' | grep -v '^$' | xargs)
else
    echo "[ERROR] .env file not found. Please copy .env.example to .env and configure it."
    exit 1
fi

echo "Starting YOLO Security Monitor on port 8000..."
echo "Access the application at: http://localhost:8000"
echo ""

uvicorn backend.main:app --host 0.0.0.0 --port 8000
