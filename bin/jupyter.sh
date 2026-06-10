#!/bin/bash
# 启动 Jupyter Notebook 服务

set -e

cd "$(dirname "$0")/.."

echo "Starting Jupyter Notebook on port 8080..."
echo "Access at: http://localhost:8080"
echo ""

jupyter notebook --port=8080 --NotebookApp.token='' --NotebookApp.password=''
