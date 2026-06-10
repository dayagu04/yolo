# YOLO 安防监控系统 - 任务管理
# 使用方法: make <target>

.PHONY: help start dev test init-db jupyter docker-up docker-down lint clean

help:
	@echo "YOLO Security Monitor - Available Commands:"
	@echo ""
	@echo "  make start       - 启动生产模式服务器"
	@echo "  make dev         - 启动开发模式服务器（热重载）"
	@echo "  make test        - 运行测试套件"
	@echo "  make init-db     - 初始化数据库"
	@echo "  make jupyter     - 启动 Jupyter Notebook"
	@echo "  make docker-up   - 启动 Docker 容器"
	@echo "  make docker-down - 停止 Docker 容器"
	@echo "  make lint        - 代码格式检查"
	@echo "  make clean       - 清理临时文件"
	@echo ""

start:
	@bash bin/start.sh

dev:
	@bash bin/dev.sh

test:
	@pytest test/ -v --tb=short

init-db:
	@python scripts/init_database.py

jupyter:
	@bash bin/jupyter.sh

docker-up:
	@docker-compose up -d

docker-down:
	@docker-compose down

lint:
	@ruff check backend/ --select E,F,W --ignore E501
	@ruff format backend/ --check

clean:
	@echo "Cleaning temporary files..."
	@find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	@find . -type f -name "*.pyc" -delete 2>/dev/null || true
	@find . -type f -name "*.pyo" -delete 2>/dev/null || true
	@find . -type f -name ".DS_Store" -delete 2>/dev/null || true
	@echo "Done!"