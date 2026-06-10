# AGENTS.md — SafeCam 智能视频监控系统

## 1. 项目概述

SafeCam 是基于 YOLOv8 的智能视频监控系统，支持多摄像头实时检测、人员追踪、ROI 区域入侵检测和多渠道告警推送。

**架构：** 前后端分离，FastAPI 同时提供 API 和静态文件服务，Docker 部署时由 Nginx 反向代理。

| 层 | 技术栈 |
|---|---|
| 后端 | Python 3.11 + FastAPI + Uvicorn + SQLAlchemy 2.0 + MySQL 8.0 |
| 前端 | 原生 HTML/CSS/JS（ES Modules，无构建工具） + ECharts 5 |
| ML | YOLOv8 (ultralytics) + PyTorch + OpenCV |
| 基础设施 | Docker Compose（backend / mysql / redis / nginx）|

## 2. 目录结构

```
backend/          # FastAPI 后端
  main.py         # 应用入口、lifespan、路由注册
  config.py       # YAML 配置加载（YOLO_* 环境变量覆盖）
  database.py     # SQLAlchemy ORM 模型 + DatabaseManager
  auth.py         # JWT 认证、登录锁定、速率限制
  schemas.py      # Pydantic 请求/响应模型
  camera.py       # CameraManager 检测与追踪
  capture_process.py  # 多进程摄像头采集（SharedMemory）
  tracker.py      # IoU + 中心点匹配追踪
  roi_detector.py # ROI 区域入侵/徘徊/聚集检测
  model_manager.py    # 多模型管理
  notifier.py     # 飞书通知
  notifiers/      # 企业微信、钉钉、邮件、Webhook 通知
  routers/        # API 路由（auth/camera/alert/roi/model/system）
  metrics.py      # Prometheus 指标
  redis_stats.py  # Redis 实时统计
  logging_system.py   # 结构化日志
frontend/         # 原生前端 SPA
  index.html      # 入口
  static/js/      # 14 个 ES Module（app.js 为主入口）
  static/css/     # 样式
test/             # pytest 测试套件
alembic/          # 数据库迁移脚本
scripts/          # 工具脚本（摄像头检查、数据库初始化、训练）
models/           # YOLO 模型权重（.pt）
config.yaml       # 应用主配置
config.test.yaml  # 测试环境配置
docker-compose.yml
```

## 3. 开发原则

1. **技术从简** — 同一问题优先选择最简洁的方案，不过度抽象
2. **文档同步** — 接口变更必须同步更新技术文档；发现文档未覆盖的已有接口需补录
3. **测试先行** — 新增/修改代码需配套测试用例，覆盖率不低于现有基线（30%）
4. **中文回答** — 日常交流用中文，报错信息和技术术语保留英文原文便于定位
5. **最小改动** — 只改任务涉及的部分，不顺手重构无关代码

## 4. 后端规范

### 4.1 代码风格

- **格式化：** Ruff（CI 使用 `ruff check` + `ruff format`）
- 提交前本地执行：
  ```bash
  ruff check backend/ --select E,F,W --ignore E501
  ruff format backend/
  ```
- **禁止：** `any` 类型、未使用的 import、硬编码魔法值（用常量或 config 替代）
- **类型注解：** 函数签名必须有参数和返回值类型注解

### 4.2 API 路由规范

- 路由前缀统一 `/api/v1/`，按模块拆分到 `backend/routers/`
- 路由注册：在 `backend/main.py` 的 `app.include_router()` 中添加
- 认证方式：依赖注入 `get_current_user` 或 `require_admin`
- 请求/响应模型：必须在 `backend/schemas.py` 中定义 Pydantic 模型
- 审计日志：关键操作调用 `audit(request, username, action)`

```python
# 路由文件标准结构
from fastapi import APIRouter, Depends, HTTPException
from backend.schemas import XxxRequest, XxxResponse
from backend.auth import get_current_user

router = APIRouter(prefix="/api/v1/xxx", tags=["模块名"])

@router.get("/", response_model=list[XxxResponse])
async def list_items(current_user=Depends(get_current_user)):
    ...
```

### 4.3 数据库规范

- ORM 模型定义在 `backend/database.py`，继承 `Base`
- 表结构变更必须通过 Alembic 迁移：`alembic revision --autogenerate -m "描述"`
- 禁止直接修改 `alembic/versions/` 中已提交的迁移文件
- 查询通过 `DatabaseManager` 方法封装，不在路由中直接写 SQL

### 4.4 配置管理

- 配置文件：`config.yaml`（主）、`config.test.yaml`（测试）、`config.secrets.yaml`（敏感）
- 环境变量覆盖：`YOLO_` 前缀（如 `YOLO_DATABASE_PASSWORD`）
- 敏感信息只放 `.env` 或 `config.secrets.yaml`，禁止硬编码到代码中

## 5. 前端规范

- **无构建工具** — 原生 ES Modules，直接在浏览器运行
- **模块组织** — `frontend/static/js/` 下按功能拆分，`app.js` 为主入口
- **新增模块：** 在 `app.js` 中 `import` 并注册到 tab 切换逻辑
- **图表：** 使用 ECharts 5（CDN 引入）
- **PWA：** 修改 `service-worker.js` 的 `CACHE_NAME` 版本号触发更新
- **样式：** 写在 `frontend/static/css/main.css`，不引入额外 CSS 框架

## 6. 测试规范

### 6.1 框架与命令

- **框架：** pytest + pytest-cov + pytest-html
- **配置：** `pytest.ini`
- 常用命令：
  ```bash
  # 运行全部测试（含覆盖率报告）
  pytest test/

  # 只跑单元测试（CI 精简模式）
  pytest test/ -m "unit" --tb=short -q --timeout=60

  # 运行指定模块
  pytest test/test_auth_unit.py -v

  # 跳过慢速测试
  pytest test/ -m "not slow"
  ```

### 6.2 测试标记

使用 `pytest.ini` 中定义的 marker 分类，新增测试必须打标记：

| 标记 | 用途 |
|---|---|
| `unit` | 单元测试（CI 默认运行） |
| `api` | API 接口测试（CI 默认运行） |
| `integration` | 集成测试 |
| `database` | 数据库测试 |
| `camera` | 摄像头相关测试 |
| `websocket` | WebSocket 测试 |
| `security` | 安全测试 |
| `slow` | 慢速测试（CI 跳过） |

### 6.3 编写要求

- 测试文件：`test/test_<模块名>_unit.py`，与业务模块对应
- 使用 `conftest.py` 中的共享 fixtures（`config`, `db_manager`, `redis_stats` 等）
- 异步测试：`asyncio_mode = auto`，直接写 `async def test_xxx()`
- 禁止：跳过必填用例、修改测试预期结果来掩盖问题
- 覆盖率报告输出到 `tmp/coverage_html/`，HTML 报告输出到 `tmp/pytest_report.html`

## 7. 禁止操作

### 7.1 不得修改/删除

- `.env`、`config.secrets.yaml` — 密钥文件
- `backend/database.py` 中已有的 ORM 模型字段（需走 Alembic 迁移）
- `alembic/versions/` 中已提交的迁移文件
- `package.json`（如有）、CI/CD 配置（`.github/workflows/`）

### 7.2 不得提交

- `node_modules/`、`__pycache__/`、`.pyc` 文件
- IDE 配置（`.vscode/`、`.idea/`）
- `models/*.pt`（模型权重文件过大，通过 `.gitignore` 排除）
- 未完成的测试代码

### 7.3 操作边界

- 修改认证、权限校验、数据加密等核心逻辑前，需生成变更方案并标记"需人类审核"
- 新增依赖前先检查 `requirements.txt`，禁止重复引入同类库
- 数据库表结构变更必须通过 `alembic revision` 生成迁移脚本

## 8. 安全规范

- 密钥管理：所有密钥存于 `.env` 或 `config.secrets.yaml`，通过 `YOLO_*` 环境变量注入
- 接口校验：所有 API 必须做参数校验（Pydantic），禁止直接拼接 SQL
- 认证：JWT Token 机制，支持登录锁定和速率限制
- 前端：禁止 `innerHTML` 拼接用户输入，使用 `textContent` 或模板渲染

## 9. CI/CD 流水线

```
push/PR to main
  ├─ lint:      ruff check + ruff format
  ├─ security:  pip-audit 依赖漏洞扫描
  ├─ test:      pytest unit + api 测试（MySQL 8.0 服务容器）
  └─ build:     Docker 镜像构建（仅 main 分支推送触发）
```

本地提交前建议执行：
```bash
ruff check backend/ --select E,F,W --ignore E501
ruff format backend/
pytest test/ -m "unit" --tb=short -q --timeout=60
```

## 10. Docker 部署

```bash
# 启动全部服务
docker-compose up -d

# 查看日志
docker-compose logs -f backend

# 数据库迁移
docker-compose exec backend alembic upgrade head
```

服务端口：Nginx 对外暴露 80（HTTP）/ 443（HTTPS），后端内部 8000。

## 11. 调试与排错

- 日志位置：`logs/` 目录，按日期分区
- 测试报告：`tmp/pytest_report.html`
- 覆盖率：`tmp/coverage_html/index.html`
- 常见问题：
  1. 启动失败 — 检查 MySQL/Redis 是否就绪，`config.yaml` 连接配置
  2. 摄像头无法连接 — 运行 `python scripts/check_camera.py` 检测
  3. 测试失败 — 确认 `config.test.yaml` 配置正确，数据库已初始化
  4. 端口冲突 — 默认 8000，修改 `docker-compose.yml` 或 `start.bat`
