# Changelog

本文件记录 SafeCam 项目的重要变更。格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)。

## [Unreleased]

### Added
- **SECURITY.md**：安全规范与最佳实践文档
- **BUGFIX_REPORT.md**：Bug 修复记录与待办事项

### Fixed
- **[CRITICAL] SQL 注入风险**（`scripts/init_database.py`）：将 f-string SQL 拼接改为参数化查询
- **[CRITICAL] Redis KEYS 命令性能问题**（`backend/redis_stats.py`）：使用 SCAN 游标替代 KEYS 命令，避免生产环境阻塞
- **[MAJOR] 布尔值比较规范**（`backend/database.py`）：修正 SQLAlchemy 布尔值比较，使用 `.is_(True/False)`
- **[MAJOR] 共享内存资源泄漏**（`backend/capture_process.py`）：改进异常处理，确保 `shm.unlink()` 总是执行
- **[MAJOR] 时区感知问题**（`backend/database.py`）：`delete_old_alerts` 使用 UTC 时区避免夏令时问题

### Changed
- README.md 添加安全章节和文档索引

## [2.0.0] - 2024-12

### Added
- 完整单元测试套件（103 个测试），覆盖 auth、roi_detector、notifiers、routers、schemas、metrics、model_manager、capture_process
- Alembic 迁移 005：外键约束和缺失索引
- MIT LICENSE 文件
- CHANGELOG 文件
- **bin/ 目录**：统一管理可执行脚本
  - `bin/start.sh` - Linux/Mac 启动脚本
  - `bin/dev.sh` - 开发模式启动脚本（热重载）
  - `bin/jupyter.sh` - Jupyter Notebook 启动脚本
  - `bin/start.bat` - Windows 启动脚本（从根目录移入）
- **扩展的 Makefile**：提供 start、dev、test、init-db、jupyter、docker-up/down、lint、clean 等命令
- **environment.yml**：Conda 环境配置，一键创建包含开发依赖的 Python 3.11 环境

### Changed
- 更新 README.md 文档，使其与实际代码同步：
  - 前端模块数量从 9 个更新为 14 个
  - 补充完整的项目结构图（包含 bin/、routers/ 目录和所有后端模块）
  - 扩展 API 端点列表，包含用户管理、系统管理等核心接口
  - 更新 config.yaml 示例，包含所有关键配置项
  - 更新数据库迁移文件列表（006 个迁移文件）
  - 更新快速开始章节，添加多种启动方式说明
- 更新 AGENTS.md 前端模块数量为 14 个
- **规范化项目目录结构**：
  - 移动 `start.bat` 到 `bin/start.bat`
  - 改进 `bin/start.bat` 环境变量加载逻辑
  - 扩展 Makefile 从单一 Jupyter 启动改为完整的任务管理工具
- 清理项目：恢复 md/ 文档子仓库

### Fixed
- CORS 中间件时序 Bug：config 在 import 时为空，导致生产域名从未生效
- 密码修改端点：JWT payload 新增 id 字段，修复非管理员无法改自己密码
- ROI 更新端点：添加字段白名单，防止覆写 id/camera_id 等不可变字段
- metrics.py：ws_clients 指标接入实际值（之前声明但从未写入）
- 审计日志：写入失败不再静默吞异常，改为 debug 日志

### Changed
- CORS methods/headers 从通配符收紧为具体值（GET/POST/PUT/DELETE/OPTIONS）
- 数据库模型：替换 deprecated declarative_base() 为 SQLAlchemy 2.0 DeclarativeBase
- Alert.camera_id 添加外键约束 → cameras.id (ON DELETE SET NULL)
- AlertEscalation.alert_id 添加外键约束 → alerts.id (ON DELETE CASCADE)
- CameraROI.camera_id 添加外键约束 → cameras.id (ON DELETE CASCADE)
- 新增索引：cameras.status、alert_escalations.notified、camera_rois.enabled
- 多进程摄像头采集（SharedMemory）
- 告警升级链（low→medium→high）
- ROI 区域检测（入侵/徘徊/聚集）
- PWA 支持（Service Worker）
- 5 个通知通道（飞书/企微/钉钉/邮件/Webhook）
- 前端 ES 模块化（13 个 JS 模块）
- 用户管理、审计日志、通知设置页面
- JWT 双令牌认证（access + refresh）
- 登录失败锁定和请求限流
- Prometheus 指标端点
- Docker Compose 部署（backend + MySQL + Redis + Nginx）

## [1.0.0] - 2024-10

### Added
- YOLOv8 实时人员检测
- 多摄像头管理
- MJPEG 视频流
- 告警系统（WebSocket 推送）
- 告警历史查询和 CSV 导出
- 截图保存和回放
- 基本的 Web 前端界面
