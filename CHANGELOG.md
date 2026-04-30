# Changelog

本文件记录 SafeCam 项目的重要变更。格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)。

## [Unreleased]

### Added
- 完整单元测试套件（103 个测试），覆盖 auth、roi_detector、notifiers、routers、schemas、metrics、model_manager、capture_process
- Alembic 迁移 005：外键约束和缺失索引
- MIT LICENSE 文件
- CHANGELOG 文件

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

## [2.0.0] - 2024-12

### Added
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
