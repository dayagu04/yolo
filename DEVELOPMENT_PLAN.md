# 开发计划 - 智能视频监控系统

## 项目概述

基于 YOLOv8 的实时视频监控系统，支持人员检测与告警。

**当前状态：**
- ✅ 阶段 1：实时视频流（FastAPI + OpenCV）
- 🚧 阶段 2：YOLO 人员检测与告警（待集成）
- ⏳ 阶段 3：IP 摄像头与多路拼接

**技术栈：**
- 后端：FastAPI + OpenCV + Ultralytics YOLOv8
- 前端：原生 HTML/CSS/JavaScript
- 模型：YOLOv8n（person_best.pt，mAP50=0.802）

---

## 阶段 2：YOLO 检测集成（当前任务）

### 2.1 后端集成 YOLO 检测

**目标：** 在视频流中实时检测人员，并在画面上绘制边界框。

**文件：** `backend/camera.py`

**实现步骤：**

1. **加载 YOLO 模型**
   ```python
   from ultralytics import YOLO
   
   class CameraManager:
       def __init__(self, camera_id=0, width=640, height=480):
           # ... 现有代码 ...
           self.model = YOLO('models/person_best.pt')
           self.model.conf = 0.5  # 置信度阈值
   ```

2. **在帧生成器中添加检测**
   
   修改 `get_frame_generator()` 方法（第 46-56 行）：
   ```python
   def get_frame_generator(self):
       while self.running:
           frame = self.get_frame()
           if frame is not None:
               # YOLO 检测
               results = self.model(frame, verbose=False)
               annotated_frame = results[0].plot()  # 绘制边界框
               
               # 编码为 JPEG
               ret, jpeg = cv2.imencode('.jpg', annotated_frame, 
                                       [cv2.IMWRITE_JPEG_QUALITY, 85])
               if ret:
                   yield (b'--frame\r\n'
                          b'Content-Type: image/jpeg\r\n\r\n' + 
                          jpeg.tobytes() + b'\r\n')
           time.sleep(0.033)
   ```

3. **性能优化（可选）**
   - 降低检测频率（每 N 帧检测一次）
   - 使用 GPU 加速（`device='cuda'`）
   - 调整输入尺寸（`imgsz=320` 更快）

**测试：**
```bash
python -m uvicorn backend.main:app --reload
# 访问 http://localhost:8000，应看到人员检测框
```

---

### 2.2 实时告警系统

**目标：** 检测到人员时，通过 WebSocket 向前端推送告警。

#### 2.2.1 后端 WebSocket 实现

**文件：** `backend/main.py`

**步骤：**

1. **安装依赖**
   ```bash
   pip install websockets
   ```
   更新 `requirements.txt`。

2. **添加 WebSocket 端点**
   ```python
   from fastapi import WebSocket
   from typing import List
   
   # 全局 WebSocket 连接池
   active_connections: List[WebSocket] = []
   
   @app.websocket("/ws")
   async def websocket_endpoint(websocket: WebSocket):
       await websocket.accept()
       active_connections.append(websocket)
       try:
           while True:
               await websocket.receive_text()  # 保持连接
       except:
           active_connections.remove(websocket)
   
   async def broadcast_alert(message: dict):
       """向所有客户端广播告警"""
       for connection in active_connections:
           try:
               await connection.send_json(message)
           except:
               pass
   ```

3. **在检测中触发告警**
   
   修改 `backend/camera.py`：
   ```python
   class CameraManager:
       def __init__(self, ..., alert_callback=None):
           # ... 现有代码 ...
           self.alert_callback = alert_callback
           self.last_alert_time = 0
       
       def get_frame_generator(self):
           while self.running:
               frame = self.get_frame()
               if frame is not None:
                   results = self.model(frame, verbose=False)
                   
                   # 检测到人员
                   if len(results[0].boxes) > 0:
                       current_time = time.time()
                       # 防止频繁告警（5秒间隔）
                       if current_time - self.last_alert_time > 5:
                           if self.alert_callback:
                               self.alert_callback({
                                   "type": "person_detected",
                                   "count": len(results[0].boxes),
                                   "timestamp": current_time
                               })
                           self.last_alert_time = current_time
                   
                   annotated_frame = results[0].plot()
                   # ... 编码输出 ...
   ```

4. **连接回调到 WebSocket**
   
   在 `backend/main.py` 中：
   ```python
   import asyncio
   
   def get_camera(camera_id: int = 0):
       if camera_id not in cameras:
           async def alert_handler(message):
               await broadcast_alert(message)
           
           cameras[camera_id] = CameraManager(
               camera_id=camera_id,
               alert_callback=lambda msg: asyncio.create_task(alert_handler(msg))
           )
           cameras[camera_id].start()
       return cameras[camera_id]
   ```

#### 2.2.2 前端 WebSocket 集成

**文件：** `frontend/index.html`

**步骤：**

1. **替换模拟告警代码**（第 74-82 行）
   ```javascript
   // 连接 WebSocket
   const ws = new WebSocket('ws://localhost:8000/ws');
   
   ws.onmessage = function(event) {
       const data = JSON.parse(event.data);
       if (data.type === 'person_detected') {
           alertBox.textContent = `⚠️ 检测到 ${data.count} 人！`;
           alertBox.style.display = 'block';
           setTimeout(() => {
               alertBox.style.display = 'none';
           }, 3000);
       }
   };
   
   ws.onerror = function(error) {
       console.error('WebSocket 错误:', error);
   };
   
   ws.onclose = function() {
       console.log('WebSocket 连接已关闭');
   };
   ```

2. **添加连接状态指示**
   ```javascript
   ws.onopen = function() {
       console.log('WebSocket 已连接');
       // 可在页面显示连接状态
   };
   ```

**测试：**
- 打开 `frontend/index.html`
- 在摄像头前移动，应看到实时告警

---

### 2.3 前端优化

**目标：** 改进 UI/UX，添加控制面板。

**功能清单：**

1. **检测统计面板**
   - 显示当前检测人数
   - 今日告警次数
   - 最后告警时间

2. **设置面板**
   - 调整检测置信度阈值
   - 开关告警声音
   - 调整告警间隔

3. **历史记录**
   - 告警日志列表
   - 可选：截图保存

**实现建议：**
- 使用 Vue.js 或 React 重构前端（可选）
- 或继续使用原生 JS + CSS Grid 布局

---

## 阶段 3：多摄像头与 IP 摄像头

### 3.1 多摄像头支持

**当前状态：** 后端已支持 `camera_id` 参数。

**前端实现：**

1. **多路视频流显示**
   ```html
   <div class="video-grid">
       <img src="http://localhost:8000/video_feed?camera_id=0">
       <img src="http://localhost:8000/video_feed?camera_id=1">
       <img src="http://localhost:8000/video_feed?camera_id=2">
       <img src="http://localhost:8000/video_feed?camera_id=3">
   </div>
   ```

2. **动态添加/移除摄像头**
   - 摄像头配置管理界面
   - 支持拖拽排序

### 3.2 IP 摄像头（RTSP）

**修改：** `backend/camera.py`

```python
class CameraManager:
    def __init__(self, camera_source, ...):
        # camera_source 可以是：
        # - 整数：本地摄像头 ID（0, 1, 2...）
        # - 字符串：RTSP URL（rtsp://user:pass@ip:port/stream）
        self.cap = cv2.VideoCapture(camera_source)
```

**配置文件：** `config.yaml`
```yaml
cameras:
  - id: 0
    name: "前门"
    source: 0
  - id: 1
    name: "后门"
    source: "rtsp://admin:password@192.168.1.100:554/stream"
  - id: 2
    name: "车库"
    source: "rtsp://admin:password@192.168.1.101:554/stream"
```

---

## 技术债务与优化

### 性能优化

1. **YOLO 推理优化**
   - [ ] 使用 TensorRT 加速（NVIDIA GPU）
   - [ ] 导出为 ONNX 格式
   - [ ] 批量处理多路视频

2. **视频流优化**
   - [ ] 使用 H.264 替代 MJPEG（降低带宽）
   - [ ] WebRTC 实现（更低延迟）
   - [ ] 自适应码率

### 功能扩展

1. **检测类别扩展**
   - 车辆检测
   - 宠物检测
   - 异常行为检测

2. **存储与回放**
   - 录像功能（按告警触发）
   - 云存储集成（OSS/S3）
   - 视频回放界面

3. **通知系统**
   - 邮件通知
   - 短信通知
   - 移动 App 推送

### 部署

1. **Docker 容器化**
   ```dockerfile
   FROM python:3.9
   WORKDIR /app
   COPY requirements.txt .
   RUN pip install -r requirements.txt
   COPY . .
   CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
   ```

2. **生产环境配置**
   - Nginx 反向代理
   - HTTPS 证书
   - 进程管理（Supervisor/systemd）

---

## 开发时间估算

| 任务 | 预计时间 |
|---|---|
| 2.1 YOLO 检测集成 | 2-4 小时 |
| 2.2 WebSocket 告警 | 4-6 小时 |
| 2.3 前端优化 | 6-8 小时 |
| 3.1 多摄像头 | 4-6 小时 |
| 3.2 IP 摄像头 | 2-3 小时 |
| 测试与调试 | 4-6 小时 |
| **总计** | **22-33 小时** |

---

## 下一步行动

### 立即开始（优先级 P0）

1. **集成 YOLO 检测到视频流**
   - 修改 `backend/camera.py`
   - 加载 `models/person_best.pt`
   - 测试检测效果

2. **实现 WebSocket 告警**
   - 后端添加 WebSocket 端点
   - 前端连接 WebSocket
   - 测试实时告警

### 短期目标（1-2 周）

- 完成阶段 2 所有功能
- 前端 UI 优化
- 编写测试用例

### 中期目标（1 个月）

- 多摄像头支持
- IP 摄像头集成
- 部署到生产环境

---

## 参考资源

- [Ultralytics YOLOv8 文档](https://docs.ultralytics.com/)
- [FastAPI WebSocket](https://fastapi.tiangolo.com/advanced/websockets/)
- [OpenCV RTSP 流](https://docs.opencv.org/4.x/dd/d43/tutorial_py_video_display.html)
