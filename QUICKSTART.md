# YOLO 安防监控系统 - 快速命令参考

## 环境准备

```bash
# Conda（推荐）
conda env create -f environment.yml
conda activate yolo

# 或 venv（要求 Python 3.11）
python3.11 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
```

## 开发命令

```bash
# 启动服务
make start          # 生产模式
make dev            # 开发模式（热重载）

# 或直接使用脚本
bash bin/start.sh   # Linux/Mac 生产模式
bash bin/dev.sh     # Linux/Mac 开发模式
bin\start.bat       # Windows

# 数据库
make init-db        # 初始化数据库
alembic upgrade head  # 执行迁移
alembic revision --autogenerate -m "描述"  # 创建新迁移

# 测试
make test           # 运行全部测试
pytest test/ -v     # 详细输出
pytest test/ -m "unit"  # 只运行单元测试

# 代码质量
make lint           # 代码检查
ruff format backend/  # 自动格式化

# 其他工具
make jupyter        # 启动 Jupyter Notebook
make docker-up      # 启动 Docker 容器
make docker-down    # 停止 Docker 容器
make clean          # 清理临时文件
```

## 项目结构

```
bin/         - 可执行脚本（start.sh, dev.sh, jupyter.sh）
backend/     - 后端代码（FastAPI + SQLAlchemy）
frontend/    - 前端代码（原生 ES Modules）
test/        - 测试套件（pytest）
scripts/     - 工具脚本（数据库初始化、摄像头检测等）
alembic/     - 数据库迁移
models/      - YOLO 模型权重
data/        - 运行时数据（截图、日志）
nginx/       - Nginx 配置
md/          - 文档子仓库
```

## 环境变量

复制 `.env.example` 到 `.env` 并配置：

```bash
# 认证
YOLO_AUTH_SECRET_KEY=your-secret-key
YOLO_AUTH_INIT_ADMIN_PASSWORD=your-admin-password

# 数据库
YOLO_DATABASE_PASSWORD=your-db-password

# Redis（可选）
YOLO_REDIS_PASSWORD=your-redis-password
```

## 常见任务

**添加新的 API 端点：**
1. 在 `backend/routers/` 中创建或编辑路由文件
2. 在 `backend/main.py` 中注册路由
3. 在 `backend/schemas.py` 中定义请求/响应模型
4. 编写测试用例

**数据库变更：**
1. 修改 `backend/database.py` 中的 ORM 模型
2. 生成迁移：`alembic revision --autogenerate -m "描述"`
3. 执行迁移：`alembic upgrade head`

**添加前端模块：**
1. 在 `frontend/static/js/` 中创建新模块
2. 在 `frontend/static/js/app.js` 中导入并注册
3. 更新 Service Worker 版本号触发缓存更新

更多详情请查看 [README.md](README.md) 和 [AGENTS.md](AGENTS.md)。
