# 智能视频监控系统 - 快速启动指南

## 启动方式

### 1. 真实环境（需要摄像头 + YOLO 模型）

```bash
# 启动后端服务
python backend/main.py

# 访问前端
http://localhost:8000
```

**要求：**
- 摄像头设备可用（默认 camera_id=0）
- YOLO 模型文件存在：`models/person_best.pt`
- 依赖已安装：`fastapi`, `uvicorn`, `opencv-python`, `ultralytics`

---

### 2. Mock 环境（前端 UI 预览，无需硬件）

```bash
# 启动 Mock 服务器
python test/mock_server.py

# 访问前端
http://localhost:8000
```

**特性：**
- 无需摄像头和 YOLO 模型
- 自动生成模拟告警事件（每 8~20 秒）
- 模拟视频流（纯色帧 + 文字）
- 适合前端开发和 UI 调试

---

## 系统架构

```
┌─────────────────────────────────────────────────────────────┐
│                         前端 (Frontend)                      │
│  - 视频播放区（MJPEG 流）                                     │
│  - 实时告警面板（WebSocket 推送）                             │
│  - 系统状态栏（Health 轮询）                                  │
│  - 日志面板（结构化日志展示）                                 │
└─────────────────────────────────────────────────────────────┘
                              ▲
                              │ HTTP + WebSocket
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                         后端 (Backend)                       │
│  - FastAPI 服务器                                            │
│  - CameraManager（视频采集 + YOLO 推理）                     │
│  - Track 去重管理器（人员追踪 + 告警去重）                   │
│  - WebSocket 信令广播                                        │
│  - 结构化日志系统                                            │
└─────────────────────────────────────────────────────────────┘
                              ▲
                              │
                    ┌─────────┴─────────┐
                    │                   │
              摄像头设备          YOLO 模型
              (cv2.VideoCapture)  (person_best.pt)
```

---

## 核心功能

### 1. 人员检测与追踪
- 基于 YOLOv8n 模型检测画面中的人员
- 轻量级 Track 关联（IoU + 中心点距离）
- 自动去重：同一人持续出现期间只告警一次

### 2. 实时告警
- 新人员进入画面时触发告警
- WebSocket 实时推送到前端
- 全局频控（5 秒冷却）防止抖动误报

### 3. 系统监控
- 摄像头连接状态
- AI 模型加载状态
- 实时 FPS 统计
- 帧延迟监控
- WebSocket 客户端数量

### 4. 结构化日志
- JSON 格式日志输出
- 内存环形缓冲（最大 500 条）
- 前端实时展示（支持按 level 过滤）

---

## API 接口

### HTTP 接口

| 方法 | 路径 | 功能 |
|------|------|------|
| GET | `/video_feed?camera_id=0` | MJPEG 视频流 |
| POST | `/api/camera/{id}/config` | 更新检测配置 |
| GET | `/api/camera/{id}/status` | 查询摄像头状态 |
| GET | `/api/logs?limit=100` | 获取最近日志 |
| GET | `/health` | 系统健康检查 |

### WebSocket 接口

| 路径 | 功能 |
|------|------|
| `/ws/alert` | 实时告警、状态、日志推送 |

**消息类型：**
- `type=alert`：人员告警事件
- `type=status`：系统状态变更
- `type=log`：结构化日志

---

## 配置参数

### 后端配置（camera.py）

```python
# Track 关联参数
_track_ttl_sec = 2.0           # Track 超时时间（秒）
_alert_cooldown_sec = 5.0      # 告警冷却时间（秒）
iou_threshold = 0.3            # IoU 匹配阈值
center_distance_threshold = 50 # 中心点距离阈值（像素）

# 检测参数
conf_threshold = 0.5           # 置信度阈值（可通过 API 动态调整）
detect_every_n = 2             # 每 N 帧检测一次（性能优化）
```

### 前端配置（index.html）

```javascript
const CAMERA_ID = 0;           // 摄像头 ID
wsRetryDelay = 2000;           // WebSocket 重连初始延迟（毫秒）
heartbeatInterval = 20000;     // 心跳间隔（毫秒）
healthCheckInterval = 5000;    // Health 轮询间隔（毫秒）
```

---

## 故障排查

### 摄像头无法打开
- 检查摄像头是否被其他程序占用
- 尝试更改 `camera_id`（0, 1, 2...）
- 查看后端日志：`camera.read_failed` 事件

### YOLO 模型加载失败
- 确认模型文件存在：`models/person_best.pt`
- 检查 ultralytics 库是否正确安装
- 查看后端日志：`model.load_failed` 事件

### WebSocket 连接失败
- 检查后端服务是否启动
- 确认端口 8000 未被占用
- 查看浏览器控制台 WebSocket 错误信息

### 前端无画面
- 检查 `/video_feed` 接口是否返回数据
- 尝试点击"刷新画面"按钮
- 查看 Network 面板确认 MJPEG 流是否正常

---

## 开发建议

### 前端开发
1. 使用 Mock 服务器进行 UI 开发：`python test/mock_server.py`
2. 修改 `frontend/index.html` 后刷新浏览器即可看到效果
3. 使用浏览器开发者工具查看 WebSocket 消息

### 后端开发
1. 修改代码后重启服务：`python backend/main.py`
2. 查看结构化日志输出（JSON 格式）
3. 使用 `/health` 接口监控系统状态

### 协议变更
1. 先更新 `md/c-s.md` 文档
2. 修改 `backend/schemas.py` 定义
3. 同步更新前后端代码
4. 确保前后端消息格式一致

---

## 文档索引

- **系统设计文档：** `md/c-s.md`
- **协议定义：** `backend/schemas.py`
- **Mock 服务器：** `test/mock_server.py`
- **前端页面：** `frontend/index.html`
- **后端主程序：** `backend/main.py`
- **摄像头管理：** `backend/camera.py`
- **日志系统：** `backend/logging_system.py`
