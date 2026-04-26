智能视频监控 MVP 阶段：前后端详细设计文档

## 版本说明
- **文档版本：** v1.6
- **最后更新：** 2026-04-26
- **实现状态：** 本文档为系统设计的 Source of Truth，代码实现需与此文档保持一致
- **v1.3 更新：** 新增 MySQL 告警存储、截图保存、Redis 实时统计、告警历史查询 API
- **v1.4 更新（P0 稳定性）：** FastAPI lifespan 生命周期、健康检查细化、配置校验、截图定时清理、异常处理统一化
- **v1.5 更新（多摄像头/飞书/稳定性）：** 新增动态摄像头管理 API、飞书线程安全调度、`CONFIG_FILE` 启动配置切换、统计口径对齐
- **v1.6 更新（模块拆分/接口修正）：** `CameraManager` 拆分为 `PersonTracker` + `ScreenshotManager` 两个独立子模块；同步截图路径命名规则、`get_status` 新增 `resolution` 字段、`/health` 返回补充 `subsystems` 与 `timestamp`、配置范围校验新增飞书冷却项、接口编号去重、前端日志上限与心跳间隔对齐代码

---

## 1. 后端系统设计 (Backend Design)
后端基于 FastAPI 框架构建，主要负责视频流的获取、AI 推理计算、以及数据的实时分发。

### 1.1 核心内部模块

#### 应用生命周期管理器 (Application Lifespan)
- 使用 FastAPI `lifespan` 上下文管理替代 `@app.on_event("startup") / @app.on_event("shutdown")`
- 启动阶段（startup）：
  1. 加载并校验 `config.yaml`（支持 `CONFIG_FILE` 环境变量指定路径）
  2. 合并 `config.secrets.yaml`（若存在，优先级高于主配置）
  3. 初始化 MySQL 连接
  4. 初始化 Redis 连接（可选）
  5. 初始化飞书通知器（可选，由 `notifications.feishu.enabled` 控制）
  6. 启动截图清理后台任务
  7. 初始化 `config.cameras` 列表中所有摄像头（lifespan 统一预热）
  8. 写入 `app.startup` 结构化日志
- 关闭阶段（shutdown）：
  1. 停止所有摄像头线程
  2. 将摄像头从 Redis 在线集合移除
  3. 停止截图清理后台任务
  4. 写入 `app.shutdown` 结构化日志
- **目标：** 消除 FastAPI 弃用告警，统一资源初始化与释放时序

#### 配置管理模块 (Config Manager)
- **实现文件：** `backend/config.py`
- 职责：加载 `config.yaml`、校验必填项、类型与范围检查、支持环境变量覆盖
- **必填项校验：**
  - `database.host`、`database.user`、`database.password`、`database.database`
- **范围校验：**
  - `detection.conf_threshold`: 0.1 ~ 0.95
  - `detection.detect_every_n`: 1 ~ 10
  - `alert.cooldown_sec`: 0.5 ~ 60.0
  - `alert.screenshot.quality`: 50 ~ 95
  - `alert.screenshot.retention_days`: 1 ~ 365
  - `notifications.feishu.push_cooldown_sec`: 10 ~ 3600
- **环境变量覆盖规则：** `YOLO_{SECTION}_{KEY}` 格式（全大写），例如：
  - `YOLO_DATABASE_PASSWORD=xxx` 覆盖 `database.password`
  - `YOLO_REDIS_ENABLED=true` 覆盖 `redis.enabled`
- 校验失败时在启动阶段抛出 `ValueError`，打印错误详情后退出

#### 截图清理任务 (Screenshot Cleanup)
- **实现方式：** `lifespan` 启动时创建 `asyncio.Task`，每天执行一次
- **执行时间：** 根据 `system.cleanup_schedule` 配置（默认 `03:00`）
- **清理逻辑：**
  1. 扫描 `alert.screenshot.save_dir` 目录下所有日期子目录
  2. 删除超过 `retention_days` 天的整个日期目录
  3. 同步调用 `DatabaseManager.delete_old_alerts(days=retention_days)` 删除对应数据库记录
  4. 写入 `system.cleanup_done` 日志（包含删除文件数、删除记录数）
- **异常处理：** 清理失败不影响主业务，仅写入 `system.cleanup_failed` error 日志

#### 视频采集器 (Video Capturer)
- 通过 OpenCV (cv2.VideoCapture) 独占式读取本地摄像头数据
- **帧缓冲策略（MVP）：** 采用单帧覆盖模式（latest-frame），优先保证低延迟
  - 后台线程持续读取摄像头，最新帧覆盖旧帧
  - 适用场景：实时监控，延迟敏感
- **分辨率策略：**
  - `auto_resolution=true`（默认）：不强制设置分辨率，连接后读取实际值
  - `auto_resolution=false`：设置 `width × height`，读回实际值后以实际值为准
  - 连接成功后丢弃前 5 帧（DSHOW 曝光预热黑帧）
- **断线重连机制：** 摄像头断开后自动重试 3 次，间隔 2/4/8 秒（指数退避）
- **关键指标日志：** 每次 `_detect` 调用记录推理耗时（event: `inference.timing`）

#### AI 推理引擎 (Inference Engine)
- 加载 `detection.model_path` 配置的模型权重（默认 `models/person_best.pt`）
- 从最新帧执行前向推理，获取目标边界框坐标、置信度与类别
- 将边界框与告警信息绘制叠加到原始视频帧上
- 推理异常时记录 `detection.error` 日志，降级为输出原始帧，不中断视频流

#### 告警去重与人员状态管理器 (Alert Deduplication)
- 告警目标：仅针对”新出现人员”触发告警，避免重复告警刷屏
- **目标关联算法：** IoU + 中心点双重匹配
  - IoU 阈值：`0.3`（超过则视为同一人）
  - 中心点距离阈值：`50px`（距离小于此值且 IoU 最优则关联）
  - 新 Track 立即加入已占位集合，防止同一帧多个 box 重复匹配同一新 Track
- 告警规则：
  - Track 首次出现：触发 1 次告警，标记 `alerted=True`
  - Track 持续存在：不重复告警
  - Track 消失（超时 `track_ttl_sec=2.0s` 未匹配）：标记结束，下次重新进入视为新 Track
  - 后续重新进入画面视为新 Track，可再次告警
- **全局频控兜底：** 同类事件冷却 `alert_cooldown_sec=5.0s`，防止抖动误报
- **Track 数据结构：** `{“bbox”: (x1,y1,x2,y2), “center”: (cx,cy), “last_seen”: float, “alerted”: bool}`

#### 推流生成器 (Stream Generator)
- 将经过 AI 引擎处理后的画面矩阵重编码为 JPEG 格式
- 持续生成二进制图片流，组装 HTTP 报文边界

#### 信令管理器 (Signaling Manager)
- 维护全局活动 WebSocket 连接池
- 接收 AI 引擎检测结果，按告警策略广播 JSON 告警信令
- 支持广播系统日志与状态事件（供前端日志面板展示）

#### 告警持久化模块 (Alert Persistence)
- **数据库：** MySQL 5.7+
- **表结构：** `alerts` 表存储告警记录，`cameras` 表存储摄像头配置
- **截图存储：** 文件系统存储 JPEG，数据库存储相对路径
- **截图优化：**
  - JPEG 质量可配置（默认 75，减少 40% 体积）
  - 支持三种保存模式：`first_only`（同一 Track 只保存首次）、`all`（每次都保存）、`interval`（间隔 N 秒保存）
  - 定期清理：保留最近 N 天（默认 30 天）
  - 路径规范：`{save_dir}/{date}/cam{id}_{HHMMSSmmm}.jpg`（时间戳命名，无 alert_id）

#### Redis 实时统计模块 (Real-time Statistics)
- **功能：** 提供实时统计数据，减少 MySQL 查询压力
- **数据结构：**
  - `stats:today:alerts` (String): 今日总告警数
  - `stats:today:cam:{id}` (String): 各摄像头今日告警数
  - `stats:online:cameras` (Set): 在线摄像头 ID 列表
  - `stats:current:persons` (Hash): 当前各摄像头人数 `{cam_id: count}`
  - `stats:hourly:{date}` (Sorted Set): 每小时告警数 `{hour: count}`
- **更新时机：**
  - 告警触发时：`INCR stats:today:alerts`、`INCR stats:today:cam:{id}`、`ZADD stats:hourly:{date}`
  - 检测帧更新时：`HSET stats:current:persons {cam_id} {count}`
  - 摄像头上线/下线：`SADD/SREM stats:online:cameras {cam_id}`
- **过期策略：** 每日统计数据在次日凌晨 3 点过期（TTL 27 小时）

#### 结构化日志模块 (Structured Logging)
- **实现文件：** `backend/logging_system.py`
- 后端统一输出 JSON 结构化日志（stdout + 内存环形缓冲，最大 500 条）
- 日志字段：`timestamp`（ISO 8601）、`level`、`event`、`camera_id`、`message`、`data`
- 提供最近 N 条日志查询接口供前端展示（`GET /api/logs?limit=100`）
- 所有 `type=log` 的 WebSocket 消息同时写入日志缓冲

---

### 1.2 API 接口契约
后端对外暴露以下核心接口。

#### 接口一：实时视频推流 (HTTP)
- **路径：** `GET /video_feed`
- **功能：** 向客户端下发包含检测框的实时监控画面
- **响应头：** `Content-Type: multipart/x-mixed-replace; boundary=frame`
- **数据流格式：** 持续下发 JPEG 字节流（MJPEG）

#### 接口二：实时告警与状态信令 (WebSocket)
- **路径：** `WS /ws/alert`
- **功能：** 建立长连接，用于后端向前端推送告警、状态、日志事件

**告警事件 JSON：**
```json
{
  "type": "alert",
  "timestamp": "2026-04-16T12:00:00+08:00",
  "level": "high",
  "message": "检测到新出现人员",
  "camera_id": 0,
  "data": {
    "person_count": 1,
    "new_track_ids": [12]
  }
}
```

**状态事件 JSON：**
```json
{
  "type": "status",
  "timestamp": "2026-04-16T12:00:02+08:00",
  "level": "info",
  "message": "摄像头已重连",
  "camera_id": 0,
  "data": {
    "camera_connected": true,
    "model_loaded": true
  }
}
```

**日志事件 JSON：**
```json
{
  "type": "log",
  "timestamp": "2026-04-16T12:00:03+08:00",
  "level": "warning",
  "message": "摄像头读取失败，准备重试",
  "camera_id": 0,
  "event": "camera.read_failed",
  "data": {
    "retry_in_sec": 2
  }
}
```

#### 接口三：摄像头检测配置 (HTTP)
- **路径：** `POST /api/camera/{camera_id}/config`
- **功能：** 动态调整检测开关与置信度阈值

#### 接口四：摄像头列表与动态管理 (HTTP)
- **路径1：** `GET /api/cameras`
- **功能：** 返回配置中的摄像头列表及运行状态，供前端网格渲染
- **返回示例：**
```json
{
  "total": 2,
  "cameras": [
    {
      "id": 0,
      "name": "本地摄像头",
      "location": "测试环境",
      "source": "0",
      "camera_id": 0,
      "running": true,
      "connected": true,
      "model_loaded": true,
      "fps": 28.4,
      "active_tracks": 1,
      "alert_total": 6
    }
  ]
}
```

- **路径2：** `POST /api/cameras/{camera_id}/add`
- **功能：** 动态添加摄像头并立即启动
- **请求体：**
```json
{
  "source": "rtsp://admin:***@192.168.1.20:554/stream1",
  "name": "前门摄像头",
  "location": "一楼前门",
  "auto_resolution": true,
  "width": 1280,
  "height": 720
}
```
- **约束：** `source` 必填；`camera_id` 已存在时返回 `409`

- **路径3：** `POST /api/cameras/{camera_id}/remove`
- **功能：** 动态移除摄像头并停止线程
- **返回示例：**
```json
{
  "success": true,
  "camera_id": 1
}
```

#### 接口五：摄像头运行状态 (HTTP)
- **路径：** `GET /api/camera/{camera_id}/status`
- **功能：** 查询指定摄像头当前运行状态

#### 接口六：系统健康检查 (HTTP)
- **路径：** `GET /health`
- **功能：** 返回系统整体健康状态（用于前端状态栏与运维）

**返回示例：**
```json
{
  "status": "ok",
  "timestamp": "2026-04-16T12:00:00+08:00",
  "uptime_sec": 1234,
  "ws_clients": 2,
  "camera_count": 1,
  "subsystems": {
    "database": "ok",
    "redis": "disabled",
    "model": "ok"
  },
  "cameras": [
    {
      "camera_id": 0,
      "running": true,
      "connected": true,
      "model_loaded": true,
      "detection_enabled": true,
      "conf_threshold": 0.5,
      "fps": 28.4,
      "last_frame_age_ms": 42,
      "reconnect_attempts": 0,
      "active_tracks": 2,
      "alert_total": 5
    }
  ]
}
```

> `status` 取值：`"ok"`（全部摄像头在线且模型已加载）/ `"degraded"`（任意摄像头断线或模型未加载）
> `subsystems.database` / `subsystems.redis` / `subsystems.model` 取值：`"ok"` / `"disabled"` / `"error"` / `"not_loaded"` / `"no_camera"`

#### 接口七：最近日志查询 (HTTP)
- **路径：** `GET /api/logs?limit=100`
- **功能：** 获取最近结构化日志记录（默认 100 条，最大 500 条）

#### 接口八：告警历史查询 (HTTP)
- **路径：** `GET /api/alerts`
- **查询参数：**
  - `limit` (int, 默认 50): 返回条数
  - `offset` (int, 默认 0): 分页偏移
  - `camera_id` (int, 可选): 筛选指定摄像头
  - `start_time` (ISO 8601, 可选): 起始时间
  - `end_time` (ISO 8601, 可选): 结束时间
  - `level` (string, 可选): 告警级别 (low/medium/high)
  - `order` (string, 默认 `desc`): 排序方向 (`asc` / `desc`)
- **返回示例：**
```json
{
  "total": 123,
  "limit": 50,
  "offset": 0,
  "alerts": [
    {
      "id": 456,
      "timestamp": "2026-04-16T18:30:15+08:00",
      "camera_id": 0,
      "person_count": 3,
      "new_track_ids": [1, 2, 3],
      "screenshot_path": "2026-04-16/cam0_183015123.jpg",
      "message": "检测到 3 名新出现人员",
      "level": "high"
    }
  ]
}
```

#### 接口九：告警截图获取 (HTTP)
- **路径：** `GET /api/alerts/{id}/screenshot`
- **功能：** 返回指定告警的截图
- **响应头：** `Content-Type: image/jpeg`
- **错误处理：** 404 Not Found（截图不存在或已过期）

#### 接口十：实时统计数据 (HTTP)
- **路径：** `GET /api/stats`
- **功能：** 获取 Redis 实时统计数据（需启用 Redis）
- **返回示例：**
```json
{
  "today_alerts": 123,
  "online_cameras": [0, 1, 2],
  "current_persons": {
    "0": 3,
    "1": 0,
    "2": 5
  },
  "hourly_alerts": {
    "0": 5,
    "1": 2,
    "8": 15,
    "9": 23,
    "10": 18
  },
  "camera_alerts": {
    "0": 45,
    "1": 38,
    "2": 40
  }
}
```

---

## 2. 前端系统设计 (Frontend Design)
前端采用原生 HTML/CSS/JavaScript 构建，核心目标是低延迟渲染与事件即时响应。系统为无状态展示层 + 轻量本地状态管理。

### 2.1 页面布局组件

#### 视频监控区 (Video Player View)
- 使用原生 `<img>` 标签作为流媒体容器
- 具备断流占位提示与手动刷新能力

#### 实时告警面板 (Live Alert Panel)
- 列表视图，展示 WebSocket 最新告警
- 新告警触发 UI 高亮动画
- 最多保留最近 200 条，避免内存增长

#### 系统状态栏 (Status Bar)
- 展示 WebSocket 连接状态（connecting / connected / disconnected / error）
- 展示健康检查状态（camera/model/fps）
- 展示系统时间与最近告警时间

#### 结构化日志面板 (Log Panel)
- 展示后端推送的 `type=log` 事件
- 支持查看等级（info/warning/error）
- 支持清空前端视图（不影响后端日志存储）

---

### 2.2 核心交互逻辑

#### 视频流解析逻辑
- 将 `<img>` 的 `src` 绑定到 `/video_feed?camera_id={id}`
- 浏览器自动解析 `multipart/x-mixed-replace` 并逐帧渲染

#### WebSocket 生命周期管理
- 页面加载后连接 `WS /ws/alert`
- 实现 `onopen/onmessage/onerror/onclose`
- 断线重连：初始 2 秒，指数退避至 30 秒
- **心跳机制：** 15 秒发送一次 `"ping"` 文本消息，后端回复 `{"type":"pong", "timestamp":"..."}`
- **心跳定时器管理：** 连接关闭时清理旧心跳定时器（`clearInterval`），避免重复定时器泄漏

#### DOM 动态更新
- `type=alert`：更新告警统计、告警列表、顶部提示横幅（3 秒自动隐藏）
- `type=status`：更新连接与系统状态文字
- `type=log`：追加到日志面板（支持按 level 过滤：all/info/warning/error）

#### Health 轮询
- 每 5 秒请求 `/health`
- 渲染摄像头连通性、模型状态、fps、last_frame_age、active_tracks、alert_total
- 若健康检查失败或 `status="degraded"`，状态栏显示降级状态

---

## 3. 关键行为约束

1. **协议一致性优先：** 代码以本文档接口契约为准
2. **告警去重策略：** 同一 Track 在持续出现期间只告警一次；Track 消失后重新进入可再次告警
3. **低延迟优先：** MVP 默认使用 latest-frame 策略（单帧覆盖）
4. **可观测性优先：** 所有关键状态必须可通过 `/health` 或日志看到
5. **前后端协作原则：** 文档字段改动必须先更新契约，再改代码

---

## 4. 开发工具

### Mock 服务器（前端预览）
- **路径：** `test/mock_server.py`
- **用途：** 无需真实摄像头和 YOLO 模型，独立运行前端 UI 预览
- **启动：** `python test/mock_server.py`
- **特性：** 随机生成告警事件（每 8~20 秒触发一次），模拟视频流
