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
- ES 模块化架构（9 个功能模块）
- 实时视频流显示
- 告警历史查询与导出
- 统计面板（ECharts 图表）
- 录像回放
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
│   ├── notifier.py            # 飞书通知
│   ├── notifiers/             # 多渠道通知
│   │   ├── wechat_work.py     # 企业微信
│   │   ├── dingtalk.py        # 钉钉
│   │   ├── email_notifier.py  # 邮件
│   │   └── webhook.py         # Webhook
│   └── schemas.py             # Pydantic 模型
├── frontend/                   # 前端资源
│   ├── index.html             # 主页面
│   ├── manifest.json          # PWA 清单
│   ├── service-worker.js      # Service Worker
│   └── static/
│       ├── css/main.css       # 样式
│       ├── js/                # ES 模块
│       │   ├── app.js         # 主入口
│       │   ├── auth.js        # 认证模块
│       │   ├── websocket.js   # WebSocket
│       │   ├── camera-grid.js # 摄像头网格
│       │   ├── stats.js       # 统计面板
│       │   ├── alerts.js      # 告警历史
│       │   ├── playback.js    # 录像回放
│       │   └── ...
│       └── icons/             # PWA 图标
├── alembic/                    # 数据库迁移
│   └── versions/
│       ├── 001_initial_schema.py
│       ├── 002_add_audit_logs.py
│       └── 003_add_escalation_and_roi.py
├── models/                     # YOLO 模型权重
├── data/                       # 截图与日志存储
├── docker-compose.yml          # Docker 编排
├── Dockerfile                  # Docker 构建
├── .github/workflows/ci.yml   # CI/CD 流水线
├── config.yaml                 # 应用配置
├── .env.example                # 环境变量模板
├── requirements.txt            # Python 依赖
└── start.bat                   # Windows 启动脚本
```

## 🚀 快速开始

### 1. 环境准备

```bash
# 克隆项目
git clone <repository-url>
cd yolo

# 创建虚拟环境
python -m venv venv
source venv/bin/activate  # Linux/Mac
# 或
venv\Scripts\activate     # Windows

# 安装依赖
pip install -r requirements.txt
```

### 2. 配置

```bash
# 复制环境变量模板
cp .env.example .env

# 编辑 .env 文件，配置以下变量：
# - YOLO_AUTH_INIT_ADMIN_PASSWORD: 管理员密码
# - DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME: 数据库配置
# - REDIS_HOST, REDIS_PORT: Redis 配置（可选）
```

### 3. 数据库初始化

```bash
# 创建数据库
mysql -u root -p -e "CREATE DATABASE safecam CHARACTER SET utf8mb4;"

# 执行迁移
alembic upgrade head
```

### 4. 启动服务

```bash
# Windows
start.bat

# Linux/Mac
python -m backend.main
```

访问 http://localhost:8000 使用系统。

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

| 端点 | 方法 | 描述 |
|------|------|------|
| `/api/v1/auth/login` | POST | 用户登录 |
| `/api/v1/auth/refresh` | POST | 刷新 Token |
| `/api/v1/cameras` | GET | 获取摄像头列表 |
| `/api/v1/alerts` | GET | 查询告警记录 |
| `/api/v1/rois` | GET/POST | ROI 配置管理 |
| `/api/v1/escalations/pending` | GET | 待处理升级 |
| `/api/v1/stats` | GET | 统计数据 |
| `/api/v1/metrics` | GET | Prometheus 指标 |
| `/video_feed` | GET | MJPEG 视频流 |
| `/playback` | GET | 录像回放流 |

## 🔧 配置说明

### config.yaml 示例

```yaml
server:
  host: "0.0.0.0"
  port: 8000

cameras:
  - id: 0
    name: "前门摄像头"
    source: 0  # 本地摄像头或 RTSP URL
    auto_resolution: true

detection:
  gpu_enabled: false
  device: "cpu"
  conf_threshold: 0.5
  detect_every_n: 2

alert:
  cooldown_sec: 30
  track_ttl_sec: 60
  screenshot:
    save_dir: "data/screenshots"
    retention_days: 30

database:
  host: "localhost"
  port: 3306
  user: "root"
  password: "password"
  database: "safecam"

notifications:
  feishu:
    enabled: false
    webhook_url: ""
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

## 📄 许可证

本项目采用 MIT 许可证 - 查看 [LICENSE](LICENSE) 文件了解详情

## 🙏 致谢

- [Ultralytics YOLOv8](https://github.com/ultralytics/ultralytics)
- [FastAPI](https://fastapi.tiangolo.com/)
- [SQLAlchemy](https://www.sqlalchemy.org/)
- [ECharts](https://echarts.apache.org/)
