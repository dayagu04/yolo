# 智能视频监控系统 (AI Video Surveillance)

基于 YOLOv8 的实时视频监控系统，支持边缘设备推理、Web端实时流查看与人员闯入告警。

## 🎯 架构设计 (四大核心模块)
1. **算法引擎：** 纯粹的图像处理与 YOLOv8 目标检测。
2. **流媒体服务：** FastAPI 驱动，负责视频流的重编码与 HTTP 广播。
3. **神经中枢：** WebSocket 信令系统，实现毫秒级告警分发。
4. **终端交互：** 纯静态前端，负责实时画面渲染与告警展示。

## 🗺️ 项目演进路线
- **MVP (当前目标) ✅：** 本地电脑摄像头 + YOLO 检测 + 网页流显示 + WebSocket 文字告警。
- **V2.0：** 引入真实局域网 IP 摄像头 (RTSP流) + 多路画面平铺显示。
- **V3.0：** 多摄像头物理拼接融合 + 3D/立体画面探索。

## 📁 目录结构
```text
yolo/
├── backend/           # FastAPI 后端服务 (流媒体与信令)
│   ├── main.py        # 路由定义与 WebSocket 管理
│   └── camera.py      # 摄像头抓取与流转发逻辑
├── frontend/          # 终端交互模块
│   └── index.html     # 监控面板
├── scripts/           # 训练与测试脚本
│   ├── train.py       # 训练脚本
│   ├── logger.py      # 日志工具
│   └── test_cam.py    # 🚨 新增：本地摄像头算法测试脚本
├── models/            # 模型权重
│   └── person_best.pt # 核心：最优人员检测模型（mAP50=0.802）
└── requirements.txt