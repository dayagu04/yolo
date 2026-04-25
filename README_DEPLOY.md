# 智能安防监控系统 - 部署文档

## 版本信息
- 系统版本: v1.3
- 更新日期: 2026-04-16
- 新增功能: MySQL 告警存储、截图保存、Redis 实时统计

---

## 环境要求

### 必需组件
- Python 3.9+
- MySQL 5.7+ 或 MariaDB 10.3+
- 摄像头设备（USB 摄像头或网络摄像头）

### 可选组件
- Redis 6.0+（用于实时统计功能）
- CUDA 11.0+（用于 GPU 加速推理）

---

## 快速开始

### 1. 安装依赖

```bash
# 克隆项目
cd n:/yolo

# 安装 Python 依赖
pip install -r requirements.txt
```

### 2. 配置 MySQL 数据库

#### 方式一：使用现有 MySQL 服务器

编辑 `config.yaml`：

```yaml
database:
  host: "localhost"
  port: 3306
  user: "root"
  password: "your_password"    # 修改为实际密码
  database: "security_monitor"
```

#### 方式二：安装 MySQL（Windows）

```powershell
# 下载 MySQL Installer
# https://dev.mysql.com/downloads/installer/

# 安装后设置 root 密码，然后更新 config.yaml
```

### 3. 初始化数据库

```bash
python scripts/init_database.py
```

输出示例：
```
============================================================
  智能安防监控系统 - 数据库初始化
============================================================

[1/3] 加载配置文件...
✓ 配置加载成功
  - 主机: localhost:3306
  - 用户: root
  - 数据库: security_monitor

[2/3] 创建数据库...
✓ 数据库 security_monitor 已存在

[3/3] 初始化表结构...
✓ 表结构初始化完成

============================================================
  ✓ 数据库初始化完成
============================================================
```

### 4. 配置系统参数

编辑 `config.yaml`，根据实际情况调整：

```yaml
camera:
  camera_id: 0                   # 摄像头设备 ID
  auto_resolution: true          # 自动获取摄像头分辨率
  width: 1280                    # auto_resolution=false 时生效
  height: 720

detection:
  conf_threshold: 0.5            # 检测置信度阈值
  detect_every_n: 1              # 每 N 帧检测一次

alert:
  cooldown_sec: 5.0              # 告警冷却时间
  screenshot:
    enabled: true
    quality: 75                  # JPEG 质量（50-95）
    save_mode: "first_only"      # first_only / all / interval
    retention_days: 30           # 截图保留天数
```

### 5. 启动服务

```bash
python backend/main.py
```

访问 http://localhost:8000

---

## Redis 实时统计（可选）

### 1. 安装 Redis

#### Windows
```powershell
# 下载 Redis for Windows
# https://github.com/tporadowski/redis/releases

# 解压后运行
redis-server.exe
```

#### Linux
```bash
sudo apt install redis-server
sudo systemctl start redis
```

### 2. 启用 Redis 统计

编辑 `config.yaml`：

```yaml
redis:
  enabled: true
  host: "localhost"
  port: 6379
  password: ""
```

### 3. 访问统计接口

```bash
curl http://localhost:8000/api/stats
```

返回示例：
```json
{
  "today_alerts": 123,
  "online_cameras": [0, 1, 2],
  "current_persons": {"0": 3, "1": 0},
  "hourly_alerts": {"8": 15, "9": 23, "10": 18},
  "camera_alerts": {"0": 45, "1": 38}
}
```

---

## API 接口文档

### 告警历史查询

```bash
GET /api/alerts?limit=50&offset=0&camera_id=0&start_time=2026-04-16T00:00:00
```

参数：
- `limit`: 返回条数（默认 50，最大 500）
- `offset`: 分页偏移（默认 0）
- `camera_id`: 筛选摄像头 ID（可选）
- `start_time`: 起始时间 ISO 8601（可选）
- `end_time`: 结束时间 ISO 8601（可选）
- `level`: 告警级别 low/medium/high（可选）

### 获取告警截图

```bash
GET /api/alerts/{alert_id}/screenshot
```

返回 JPEG 图片。

### 实时统计数据

```bash
GET /api/stats
```

需启用 Redis。

---

## 故障排查

### 1. 摄像头黑屏

**症状**: 视频流显示黑屏

**解决方案**:
```bash
# 运行摄像头诊断工具
python scripts/check_camera.py

# 如果提示占用，终止占用进程
python scripts/check_camera.py --kill
```

### 2. 数据库连接失败

**症状**: `数据库连接失败: (2003, "Can't connect to MySQL server")`

**解决方案**:
1. 检查 MySQL 服务是否启动
2. 检查 `config.yaml` 中的用户名/密码
3. 检查防火墙是否阻止 3306 端口

### 3. Redis 连接失败

**症状**: `Redis 连接失败: Error 10061`

**解决方案**:
1. 检查 Redis 服务是否启动
2. 设置 `redis.enabled: false` 禁用 Redis（系统仍可正常运行）

### 4. 端口 8000 被占用

**症状**: `OSError: [WinError 10048] 通常每个套接字地址只允许使用一次`

**解决方案**:
```bash
# 查找占用进程
netstat -ano | findstr :8000

# 终止进程（替换 PID）
taskkill /F /PID <PID>
```

---

## 性能优化

### 1. GPU 加速

编辑 `config.yaml`：

```yaml
detection:
  device: "cuda"    # 或 "cuda:0"
```

需要安装 CUDA 和对应版本的 PyTorch。

### 2. 降低检测频率

```yaml
detection:
  detect_every_n: 2    # 每 2 帧检测一次（降低 CPU 占用）
```

### 3. 调整截图质量

```yaml
alert:
  screenshot:
    quality: 70    # 降低质量可减少 30-40% 存储空间
```

---

## 多摄像头部署

### 1. 配置多个摄像头

```yaml
# 主摄像头
camera:
  camera_id: 0

# 在代码中动态添加更多摄像头
# 访问 /video_feed?camera_id=1
# 访问 /video_feed?camera_id=2
```

### 2. 数据库自动支持多摄像头

告警记录会自动关联 `camera_id`，查询时可按摄像头筛选。

---

## 定期维护

### 1. 清理过期截图

系统会自动清理超过 `retention_days` 的截图（默认 30 天）。

手动清理：
```bash
# 删除 30 天前的截图
python scripts/cleanup_screenshots.py --days 30
```

### 2. 数据库备份

```bash
# 备份数据库
mysqldump -u root -p security_monitor > backup_$(date +%Y%m%d).sql

# 恢复数据库
mysql -u root -p security_monitor < backup_20260416.sql
```

---

## 生产环境部署

### 1. 使用 systemd（Linux）

创建 `/etc/systemd/system/security-monitor.service`：

```ini
[Unit]
Description=Security Monitor Service
After=network.target mysql.service

[Service]
Type=simple
User=your_user
WorkingDirectory=/path/to/yolo
ExecStart=/usr/bin/python3 backend/main.py
Restart=always

[Install]
WantedBy=multi-user.target
```

启动服务：
```bash
sudo systemctl enable security-monitor
sudo systemctl start security-monitor
```

### 2. 使用 Docker（推荐）

```dockerfile
# Dockerfile
FROM python:3.9-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
CMD ["python", "backend/main.py"]
```

```yaml
# docker-compose.yml
version: '3.8'
services:
  app:
    build: .
    ports:
      - "8000:8000"
    volumes:
      - ./data:/app/data
      - ./screenshots:/app/screenshots
    depends_on:
      - mysql
      - redis

  mysql:
    image: mysql:8.0
    environment:
      MYSQL_ROOT_PASSWORD: your_password
      MYSQL_DATABASE: security_monitor
    volumes:
      - mysql_data:/var/lib/mysql

  redis:
    image: redis:7-alpine

volumes:
  mysql_data:
```

启动：
```bash
docker-compose up -d
```

---

## 技术支持

- 文档: `md/c-s.md`（协议规范）
- 问题反馈: 项目 Issues
- 配置示例: `config.yaml`
