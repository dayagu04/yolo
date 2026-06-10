# Changelog

本文件记录 SafeCam 项目的重要变更。格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)。

## [Unreleased]

### Added
- **SECURITY.md**：安全规范与最佳实践文档
- **frontend/static/js/utils.js**：前端工具模块（HTML 转义、日期格式化、安全 DOM 操作）
- **test/test_password_validation.py**：密码强度验证测试套件（20 个测试用例）
- **test/test_multi_camera_integration.py**：多摄像头集成测试（12 个测试用例）
- **backend/auth.py**：`validate_password_strength()` 密码强度验证函数

### Fixed
- **[CRITICAL] Alembic 迁移链断裂**（`alembic/versions/005`）：`down_revision` 从 `"004"` 修正为 `"004_add_alert_acknowledged"`，此前全部迁移无法执行
- **[CRITICAL] alerts.camera_id 非空与 SET NULL 外键冲突**（`alembic/versions/001`, `005`）：迁移 001 改为 nullable，迁移 005 增加 alter_column，避免 InnoDB 1830 错误
- **[MAJOR] 徘徊告警重复触发**（`backend/roi_detector.py`）：增加 `alerted_loitering` 标志，达到阈值仅触发一次
- **[MAJOR] ROI 跟踪记录内存泄漏**（`backend/roi_detector.py`）：`check_all` 中按量触发 `cleanup_stale_tracks`（此前从未被调用）
- **[MAJOR] 告警升级未过滤已确认告警**（`backend/database.py`）：`get_unprocessed_alerts` 增加 `acknowledged.is_(False)` 过滤
- **[MAJOR] WebSocket 鉴权失败后无限重连**（`frontend/static/js/websocket.js`）：4001 关闭码停止重连，新增 `closeWS()` 并在 401 时调用
- **[MAJOR] _broadcast 遍历时并发修改列表**（`backend/main.py`）：遍历 `list(_ws_clients)` 快照
- **[MAJOR] nginx 登录限流规则失效**（`nginx/nginx.conf`）：`/api/auth/login` 修正为 `/api/v1/auth/login`，并补充 `/playback`、`/static/`、PWA、`/metrics` 代理
- **[MAJOR] Docker 环境变量错配**（`.env.example`）：`YOLO_DATABASE_NAME` 修正为生效的 `YOLO_DATABASE_DATABASE`，对齐数据库名 `security_monitor`，补充 Docker 主机名说明
- **[MAJOR] Service Worker 漏缓存 utils.js**（`frontend/service-worker.js`）：补入 `utils.js`，缓存版本升至 v4
- **[MINOR] 前后端密码规则不一致**（`frontend/static/js/user-mgmt.js`, `utils.js`）：前端校验对齐后端 8 位+大小写+数字
- **[MINOR] 审计日志筛选框翻页被清空**（`frontend/static/js/audit-logs.js`）：渲染后恢复筛选值
- **[MINOR] roi-draw 非数组响应崩溃**（`frontend/static/js/roi-draw.js`）：增加 `Array.isArray` 守卫
- **[MINOR] playback 升级徽章空值崩溃**（`frontend/static/js/playback.js`）：`level` 空值守卫
- **[MINOR] 死代码清理**（`backend/camera.py`）：移除从未调用的 `_get_adaptive_detect_interval` 及孤立属性
- **[MINOR] ORM 与 Alembic 建表分歧**（`backend/database.py`）：ORM 补充 `ix_alerts_cam_level_ts` 复合索引和 `acknowledged` 索引，与迁移 006 对齐
- **[MINOR] init_database.py 提示修正**：启动端口 9000→8000，移除不存在的 `config.yaml.example` 引用
- **[CRITICAL] SQL 注入风险**（`scripts/init_database.py`）：将 f-string SQL 拼接改为参数化查询
- **[CRITICAL] Redis KEYS 命令性能问题**（`backend/redis_stats.py`）：使用 SCAN 游标替代 KEYS 命令，避免生产环境阻塞
- **[MAJOR] 布尔值比较规范**（`backend/database.py`）：修正 SQLAlchemy 布尔值比较，使用 `.is_(True/False)`
- **[MAJOR] 共享内存资源泄漏**（`backend/capture_process.py`）：改进异常处理，确保 `shm.unlink()` 总是执行
- **[MAJOR] 时区感知问题**（`backend/database.py`）：`delete_old_alerts` 使用 UTC 时区避免夏令时问题
- **[HIGH] 前端 XSS 风险**（`frontend/static/js/alerts.js`, `logs.js`）：使用 DOM API 和 textContent 代替 innerHTML
- **[HIGH] 密码复杂度验证不足**（`backend/routers/auth.py`）：要求 8 位以上 + 大小写字母 + 数字

### Changed
- README.md 添加安全章节和文档索引
- **backend/camera.py**：添加 CameraManager 类和方法的完整文档字符串
- **backend/camera.py**：整理导入顺序符合 PEP8 规范

### Improved
- 测试覆盖率：从 103 个测试提升到 135 个测试（+31%）
- 代码文档：类文档字符串覆盖率提升 33%
- 安全性：修复 2 个 CRITICAL + 5 个 MAJOR 安全问题

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
