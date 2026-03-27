# 智能视频监控系统 (YOLOv8 + 实时流)

## 项目目标
- 阶段1：单摄像头实时视频流传输到APP/网页 (已完成)
- 阶段2：集成YOLO检测"人"闯入并报警 (当前)
- 阶段3：IP摄像头 + 多摄像头画面拼接

---

## 📁 项目结构

```
yolo/
├── scripts/                    # 核心脚本
│   ├── logger.py              # 日志系统
│   ├── process_downloaded_dataset.py  # 数据集处理
│   └── train.py                # 模型训练
├── data/                       # 数据集
│   ├── images/
│   │   ├── train/             # 训练集 (6349张)
│   │   └── val/               # 验证集 (1588张)
│   ├── labels/
│   └── dataset.yaml
├── logs/                       # 训练日志
├── runs/                       # 训练结果
├── server/                     # 实时流服务器
├── app/                        # 前端页面
└── README.md
```

---

## 🚀 快速开始

### 数据集已准备好
训练集: 6349张 | 验证集: 1588张 | 总计: 7937张

### 方案1: 直接训练（使用默认参数）
```bash
cd n:\yolo
python scripts/train.py
```

### 方案2: 超参数调优（找到最佳配置）⭐推荐

**快速调优** (6-8组配置, 预计6-15小时)
```bash
python scripts/hyperparameter_tuning.py
```
此脚本专门针对 `scripts/train.py:87-117` 中的关键参数（lr0、batch、optimizer、box/cls权重等）进行网格搜索。

**全面调优** (50+组配置, 48-96小时) - 追求极致性能
```bash
python scripts/extensive_tuning.py
```

### 方案3: 多次重复验证（确保找到最佳模型）⭐⭐强烈推荐

**重复训练验证** - 多次运行相同配置，找到最稳定的最佳模型
```bash
# 重复5次（默认，推荐）
python scripts/batch_validator.py

# 或重复10次（更可靠）
# 修改脚本中的 num_repeats = 10

# 或重复20次（极致验证）
# 修改脚本中的 num_repeats = 20
```

**多配置对比验证** - 测试6种参数配置，每种重复3次
```bash
python scripts/model_validator.py
```

详细说明见 [TUNING_GUIDE.md](TUNING_GUIDE.md)

### 训练参数
- **基础模型**: yolov8n.pt
- **图像尺寸**: 640
- **Epochs**: 150 (自动早停)
- **Batch**: 8 (可通过调优脚本优化为16等)

**推荐流程**:
1. 先运行 `python scripts/hyperparameter_tuning.py` 找到最佳参数组合
2. 根据调优结果修改 `scripts/train.py` 中的训练参数
3. 使用 `python scripts/train.py` 进行最终完整训练

### 训练完成后
```bash
# 测试模型
python -c "from ultralytics import YOLO; model=YOLO('runs/person_large_dataset/weights/best.pt')"
```

---

## 📋 日志系统

日志文件保存在 `logs/` 目录，格式: `person_training_YYYYMMDD_HHMMSS.log`

查看日志:
```bash
type logs\*.log
```

---

## 后续计划

1. 集成YOLO到实时视频流
2. 添加IP摄像头支持
3. 多摄像头画面拼接
