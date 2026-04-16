智能视频监控 MVP 阶段：前后端详细设计文档

## 版本说明
- **文档版本：** v1.2
- **最后更新：** 2026-04-16
- **实现状态：** 本文档为系统设计的 Source of Truth，代码实现需与此文档保持一致

---

## 1. 后端系统设计 (Backend Design)
后端基于 FastAPI 框架构建，主要负责视频流的获取、AI 推理计算、以及数据的实时分发。

### 1.1 核心内部模块

#### 视频采集器 (Video Capturer)
- 通过 OpenCV (cv2.VideoCapture) 独占式读取本地摄像头数据
- **帧缓冲策略（MVP）：** 采用单帧覆盖模式（latest-frame），优先保证低延迟
  - 后台线程持续读取摄像头，最新帧覆盖旧帧
  - 适用场景：实时监控，延迟敏感
  - V2.0 计划：可选 bounded queue 模式，适用于录制/回放场景
- **断线重连机制：** 摄像头断开后自动重试 3 次，间隔 2/4/8 秒（指数退避）

#### AI 推理引擎 (Inference Engine)
- 加载 `person_best.pt` 模型权重
- 从最新帧执行前向推理，获取目标边界框坐标、置信度与类别
- 将边界框与告警信息绘制叠加到原始视频帧上

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

#### 接口四：摄像头运行状态 (HTTP)
- **路径：** `GET /api/camera/{camera_id}/status`
- **功能：** 查询指定摄像头当前运行状态

#### 接口五：系统健康检查 (HTTP)
- **路径：** `GET /health`
- **功能：** 返回系统整体健康状态（用于前端状态栏与运维）

**返回示例：**
```json
{
  "status": "ok",
  "uptime_sec": 1234,
  "ws_clients": 2,
  "camera_count": 1,
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

#### 接口六：最近日志查询 (HTTP)
- **路径：** `GET /api/logs?limit=100`
- **功能：** 获取最近结构化日志记录（默认 100 条，最大 500 条）

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
- 最多保留最近 50 条，避免内存增长

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
- **心跳机制：** 20 秒发送一次 `"ping"` 文本消息，后端回复 `{"type":"pong", "timestamp":"..."}`
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
