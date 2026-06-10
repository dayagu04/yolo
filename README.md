# 智能视频监控系统 (AI Video Surveillance)

基于 YOLOv8 的实时视频监控系统，支持多摄像头采集、人员检测跟踪、ROI 区域入侵检测、告警升级通知、PWA 离线访问等功能。

## 🎯 核心功能

### 实时检测与跟踪
- YOLOv8 人员检测，支持 GPU/CPU 推理
- IoU + 中心点双匹配人员跟踪
- 自适应跳帧 + 推理缓存优化

### 多摄像头管理
- 支持本地摄像头和 RTSP 网络流
- 多进程采集（SharedMemory 共享内存）
- 自动重连与指数退避

### 告警系统
- 新人员出现告警
- ROI 区域入侵检测
- 徘徊行为检测
- 人员聚集检测
- 告警自动升级链（low → medium → high）
- 多渠道通知：飞书、企业微信、钉钉、邮件、Webhook

### 数据持久化
- MySQL 数据库（SQLAlchemy ORM）
- Alembic 数据库迁移
- Redis 实时统计
- 截图与告警记录存储

### 安全特性
- JWT 认证（Access Token + Refresh Token）
- 登录失败锁定
- API 限流
- 审计日志

### 前端功能
- ES 模块化架构（14 个功能模块）
- 实时视频流显示
- 告警历史查询与导出
- 统计面板（ECharts 图表）
- 录像回放
- 用户管理界面
- 摄像头动态管理
- ROI 区域绘制工具
- 审计日志查看
- 通知渠道配置
- 实时日志面板
- PWA 离线支持

## 🗺️ 版本演进

### V1.0 (已完成)
- ✅ 基础人员检测与跟踪
- ✅ WebSocket 实时告警
- ✅ Web 管理界面
- ✅ 数据库持久化
- ✅ 飞书通知

### V2.0 (已完成)
- ✅ 多进程摄像头采集
- ✅ 自适应跳帧与推理缓存
- ✅ 告警升级链
- ✅ ROI 区域检测（入侵/徘徊/聚集）
- ✅ 录像回放
- ✅ PWA 支持
- ✅ 多通知渠道（企微/钉钉/邮件/Webhook）
- ✅ API 版本化（/api/v1/）

### V3.0 (规划中)
- 🔄 多摄像头拼接融合
- 🔄 3D 立体画面
- 🔄 行为分析（跌倒、打架等）
- 🔄 边缘计算优化

## 📁 项目结构

```text
yolo/
├── bin/                        # 可执行脚本
│   ├── start.sh               # Linux/Mac 启动脚本
│   ├── start.bat              # Windows 启动脚本
│   ├── dev.sh                 # 开发模式（热重载）
│   └── jupyter.sh             # Jupyter Notebook
├── backend/                    # FastAPI 后端服务
│   ├── main.py                # 路由定义与生命周期管理
│   ├── camera.py              # 摄像头管理与检测逻辑
│   ├── capture_process.py     # 多进程采集模块
│   ├── roi_detector.py        # ROI 区域检测
│   ├── tracker.py             # 人员跟踪器
│   ├── database.py            # 数据库 ORM 模型
│   ├── auth.py                # JWT 认证
│   ├── config.py              # 配置加载
│   ├── metrics.py             # Prometheus 指标
│   ├── model_manager.py       # 多模型管理
│   ├── logging_system.py      # 结构化日志系统
│   ├── screenshot.py          # 截图管理模块
│   ├── redis_stats.py         # Redis 统计
│   ├── notifier.py            # 飞书通知
│   ├── schemas.py             # Pydantic 模型
│   ├── notifiers/             # 多渠道通知
│   │   ├── base.py            # 通知基类
│   │   ├── wechat_work.py     # 企业微信
│   │   ├── dingtalk.py        # 钉钉
│   │   ├── email_notifier.py  # 邮件
│   │   └── webhook.py         # Webhook
│   └── routers/               # API 路由模块
│       ├── auth.py            # 用户认证与管理
│       ├── camera.py          # 摄像头管理
│       ├── alert.py           # 告警管理
│       ├── roi.py             # ROI 配置
│       ├── model.py           # 模型管理
│       ├── system.py          # 系统管理
│       └── deps.py            # 依赖注入
├── frontend/                   # 前端资源
│   ├── index.html             # 主页面
│   ├── manifest.json          # PWA 清单
│   ├── service-worker.js      # Service Worker
│   └── static/
│       ├── css/main.css       # 样式
│       └── js/                # ES 模块（14个）
│           ├── app.js         # 主入口
│           ├── auth.js        # 认证模块
│           ├── websocket.js   # WebSocket 连接
│           ├── camera-grid.js # 摄像头网格
│           ├── camera-mgmt.js # 摄像头管理
│           ├── stats.js       # 统计面板
│           ├── alerts.js      # 告警历史
│           ├── playback.js    # 录像回放
│           ├── user-mgmt.js   # 用户管理
│           ├── roi-draw.js    # ROI 绘制工具
│           ├── audit-logs.js  # 审计日志
│           ├── logs.js        # 实时日志
│           ├── notifications.js # 通知配置
│           └── toast.js       # 通知组件
├── alembic/                    # 数据库迁移
│   └── versions/
│       ├── 001_initial_schema.py
│       ├── 002_add_audit_logs.py
│       ├── 003_add_escalation_and_roi.py
│       ├── 004_add_alert_acknowledged.py
│       ├── 005_add_foreign_keys_and_indexes.py
│       └── 006_add_alert_composite_index.py
├── models/                     # YOLO 模型权重
├── data/                       # 数据集配置 + 运行时数据（截图/日志）
├── scripts/                    # 工具脚本
│   ├── init_database.py       # 数据库初始化
│   ├── check_camera.py        # 摄像头连通性检测
│   ├── train.py               # 本地模型训练
│   ├── demo_camera.py         # 本地摄像头实时检测演示
│   ├── check_feishu.py        # 飞书推送手工测试
│   ├── function.py            # 飞书消息功能函数库
│   └── logger.py              # 日志工具
├── test/                       # 测试套件
├── nginx/                      # Nginx 配置
│   └── nginx.conf
├── md/                         # 文档子仓库
├── docker-compose.yml          # Docker 编排
├── Dockerfile                  # Docker 构建
├── Makefile                    # 任务管理
├── config.yaml                 # 应用配置
├── config.test.yaml            # 测试配置
├── .env.example                # 环境变量模板
├── requirements.txt            # Python 依赖
├── pytest.ini                  # 测试配置
├── alembic.ini                 # 数据库迁移配置
├── README.md                   # 项目说明
├── CHANGELOG.md                # 变更日志
├── AGENTS.md                   # 开发规范
└── LICENSE                     # MIT 许可证
```

## 🚀 快速开始

### 1. 环境准备

```bash
# 克隆项目
git clone <repository-url>
cd yolo

# 初始化子仓库（文档）
git submodule update --init --recursive
```

**方式 A：使用 Conda（推荐）**

```bash
# 一键创建包含所有依赖的环境
conda env create -f environment.yml
conda activate yolo
```

**方式 B：使用 venv + pip**

```bash
# 创建虚拟环境（要求 Python 3.11）
python3.11 -m venv venv
source venv/bin/activate  # Linux/Mac
# 或
venv\Scripts\activate     # Windows

# 安装依赖
pip install -r requirements.txt        # 仅运行时依赖
# 如需运行测试 / 代码检查，改装开发依赖（已包含运行时依赖）
pip install -r requirements-dev.txt
```

### 2. 配置

```bash
# 复制环境变量模板
cp .env.example .env
```

编辑 `.env`，所有变量统一使用 `YOLO_` 前缀（详见 [.env.example](.env.example)），至少需配置：

```bash
# 认证（必填）
YOLO_AUTH_SECRET_KEY=<32 字节随机十六进制字符串>
YOLO_AUTH_INIT_ADMIN_PASSWORD=<管理员初始密码>

# 数据库（必填）
YOLO_DATABASE_HOST=localhost        # Docker 部署时改为服务名 mysql
YOLO_DATABASE_PORT=3306
YOLO_DATABASE_USER=root
YOLO_DATABASE_PASSWORD=<数据库密码>
YOLO_DATABASE_DATABASE=security_monitor   # 须与 docker-compose.yml 的 MYSQL_DATABASE 一致

# Redis（可选）
YOLO_REDIS_HOST=localhost           # Docker 部署时改为服务名 redis
YOLO_REDIS_PORT=6379
YOLO_REDIS_PASSWORD=
```

### 3. 数据库初始化

```bash
# 创建数据库（名称须与 YOLO_DATABASE_DATABASE 一致）
mysql -u root -p -e "CREATE DATABASE security_monitor CHARACTER SET utf8mb4;"

# 执行迁移
alembic upgrade head

# 或使用脚本一键初始化
make init-db
```

### 4. 启动服务

```bash
# 方式 1: 使用 Makefile（推荐）
make start          # 生产模式
make dev            # 开发模式（热重载）

# 方式 2: 使用脚本
bash bin/start.sh   # Linux/Mac 生产模式
bash bin/dev.sh     # Linux/Mac 开发模式
bin\start.bat       # Windows 生产模式

# 方式 3: 直接运行
python -m backend.main
```

访问 http://localhost:8000 使用系统。

## 📋 常用命令

项目通过 [Makefile](Makefile) 封装了常用操作，也可直接调用底层脚本：

```bash
# ── 服务 ──
make start            # 生产模式
make dev              # 开发模式（热重载）
bash bin/start.sh     # Linux/Mac 生产模式（make 的底层脚本）
bin\start.bat         # Windows 生产模式

# ── 数据库 ──
make init-db                                  # 初始化数据库
alembic upgrade head                          # 执行迁移
alembic revision --autogenerate -m "描述"     # 生成新迁移

# ── 测试 ──
make test                  # 运行全部测试
pytest test/ -m "unit"     # 仅单元测试
pytest test/ -m "api"      # 仅 API 测试

# ── 代码质量 ──
make lint                  # ruff 检查 + 格式校验
ruff format backend/       # 自动格式化

# ── 其他 ──
make jupyter               # 启动 Jupyter Notebook（本地训练/调试）
make docker-up             # 启动 Docker 容器
make docker-down           # 停止 Docker 容器
make clean                 # 清理 __pycache__ / *.pyc / .DS_Store
```

> 模型训练在本地进行，不在 Docker 中执行。训练脚本见 [scripts/train.py](scripts/train.py)，数据集路径配置见 [data/dataset.yaml](data/dataset.yaml)。

## 🛠️ 常见开发任务

**添加新的 API 端点**
1. 在 `backend/routers/` 中创建或编辑路由文件
2. 在 `backend/main.py` 中注册路由
3. 在 `backend/schemas.py` 中定义请求/响应模型
4. 在 `test/` 中补充测试用例

**数据库结构变更**
1. 修改 `backend/database.py` 中的 ORM 模型
2. 生成迁移：`alembic revision --autogenerate -m "描述"`
3. 检查生成的迁移文件，确认 `down_revision` 链正确
4. 执行迁移：`alembic upgrade head`

**添加前端模块**
1. 在 `frontend/static/js/` 中创建新模块
2. 在 `frontend/static/js/app.js` 中导入并注册
3. 更新 `frontend/service-worker.js` 的缓存版本号以触发更新

更详细的架构约定与编码规范见 [AGENTS.md](AGENTS.md)。

## 🐳 Docker 部署

```bash
# 构建并启动所有服务
docker-compose up -d

# 查看日志
docker-compose logs -f app

# 停止服务
docker-compose down
```

## 📡 API 文档

启动服务后访问：
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

### 主要 API 端点

完整的 API 文档请访问 `/docs`（Swagger UI）或 `/redoc`（ReDoc）。

**核心端点：**

| 端点 | 方法 | 描述 |
|------|------|------|
| `/api/v1/auth/login` | POST | 用户登录 |
| `/api/v1/auth/refresh` | POST | 刷新 Token |
| `/api/v1/auth/me` | GET | 获取当前用户信息 |
| `/api/v1/auth/users` | GET/POST | 用户列表 / 创建用户 |
| `/api/v1/cameras` | GET | 获取摄像头列表 |
| `/api/v1/cameras/{id}` | PUT | 更新摄像头配置 |
| `/api/v1/cameras/{id}/add` | POST | 添加摄像头 |
| `/api/v1/alerts` | GET | 查询告警记录 |
| `/api/v1/alerts/{id}/acknowledge` | POST | 确认告警 |
| `/api/v1/rois` | GET/POST | ROI 配置管理 |
| `/api/v1/rois/{id}` | PUT/DELETE | 更新/删除 ROI |
| `/api/v1/escalations/pending` | GET | 待处理升级 |
| `/api/v1/stats` | GET | 统计数据 |
| `/api/v1/stats/trend` | GET | 趋势数据 |
| `/api/v1/system/resources` | GET | 系统资源使用 |
| `/api/v1/audit-logs` | GET | 审计日志 |
| `/api/v1/models` | GET | 模型列表 |
| `/api/v1/notifications/config` | GET | 通知配置 |
| `/api/v1/metrics` | GET | Prometheus 指标 |
| `/video_feed` | GET | MJPEG 视频流 |
| `/playback` | GET | 录像回放流 |
| `/health` | GET | 健康检查 |

## 🔧 配置说明

### config.yaml 示例

```yaml
# 认证配置
auth:
  access_token_expire_minutes: 60
  init_admin_username: "admin"
  cors_origins:
    - "http://localhost:8000"

# 摄像头配置
cameras:
  - id: 0
    name: "前门摄像头"
    source: 0  # 本地摄像头或 RTSP URL
    location: "一楼大厅"
    auto_resolution: true

# 检测配置
detection:
  model_path: "models/person_best.pt"
  gpu_enabled: false
  device: "cpu"
  conf_threshold: 0.5
  detect_every_n: 2

# 告警配置
alert:
  cooldown_sec: 30
  track_ttl_sec: 60
  screenshot:
    enabled: true
    quality: 75
    save_mode: "first_only"  # first_only / all / interval
    interval_sec: 10
    retention_days: 30
    crop_detection: false
    save_dir: "data/screenshots"

# 数据库配置
database:
  type: "mysql"
  host: "localhost"
  port: 3306
  user: "root"
  password: ""  # 通过环境变量注入
  database: "security_monitor"
  charset: "utf8mb4"
  pool_size: 5
  pool_recycle: 3600

# Redis 配置（可选）
redis:
  enabled: false
  host: "localhost"
  port: 6379
  password: ""
  db: 0

# 通知配置
notifications:
  feishu:
    enabled: false
    webhook_url: ""
    push_cooldown_sec: 60
    push_level: "high"  # low / medium / high
    include_screenshot: true
  wechat_work:
    enabled: false
    webhook_url: ""
  dingtalk:
    enabled: false
    webhook_url: ""
  email:
    enabled: false
    smtp_host: ""
    smtp_port: 465
    username: ""
    password: ""
    to_addrs: []

# 服务器配置
server:
  host: "0.0.0.0"
  port: 8000
  log_level: "info"

# 系统配置
system:
  cleanup_schedule: "03:00"  # 每日清理时间
  max_log_buffer: 500
```

## 📊 监控指标

访问 `/metrics` 获取 Prometheus 格式指标：

- `camera_fps`: 摄像头帧率
- `camera_connected`: 连接状态
- `active_tracks`: 活跃跟踪数
- `alert_total`: 告警总数
- `cpu_percent`: CPU 使用率
- `memory_percent`: 内存使用率

## 🤝 贡献指南

1. Fork 项目
2. 创建功能分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 创建 Pull Request

详细的开发规范请查看 [AGENTS.md](AGENTS.md)。

## 🔒 安全

安全性是本项目的重要关注点。如发现安全漏洞，请查看 [SECURITY.md](SECURITY.md) 了解报告流程和最佳实践。

主要安全特性：
- JWT 认证 + Token 刷新机制
- 登录失败锁定与速率限制
- SQL 注入防护（参数化查询）
- 敏感配置环境变量注入
- 审计日志记录

## 📄 许可证

本项目采用 MIT 许可证 - 查看 [LICENSE](LICENSE) 文件了解详情

## 📚 相关文档

- [CHANGELOG.md](CHANGELOG.md) - 版本变更记录
- [AGENTS.md](AGENTS.md) - 开发规范与架构说明
- [SECURITY.md](SECURITY.md) - 安全规范与最佳实践

## 🙏 致谢

- [Ultralytics YOLOv8](https://github.com/ultralytics/ultralytics)
- [FastAPI](https://fastapi.tiangolo.com/)
- [SQLAlchemy](https://www.sqlalchemy.org/)
- [ECharts](https://echarts.apache.org/)
