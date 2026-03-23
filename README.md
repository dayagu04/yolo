# 智能视频监控系统 (YOLOv8 + 实时流)

## 项目目标
- 阶段1：单摄像头实时视频流传输到APP/网页
- 阶段2：集成YOLO检测“人”闯入并报警（**当前重点**）
- 阶段3：IP摄像头 + 多摄像头画面拼接

---

## 第一步：训练Person检测模型（已按您的要求完成）

### 1. 更新后的训练配置

`data/dataset.yaml` 已修改为：
```yaml
nc: 1
names: ['person']
```

`train.py` 已优化为适合person检测的训练脚本。

### 2. 训练模型详细步骤

#### 方式一：使用公开数据集（推荐新手）

Ultralytics YOLOv8 支持直接使用COCO数据集中的person类别进行训练。

**快速开始训练（使用预训练权重微调）：**

```bash
# 1. 确保依赖已安装
pip install -r requirements.txt

# 2. 开始训练
python train.py
```

**训练完成后模型位置：**
- 最佳模型：`runs/person_detect/weights/best.pt`
- 最后模型：`runs/person_detect/weights/last.pt`

#### 方式二：使用自己的数据集（后续推荐）

1. 收集大量包含“人”的图片（不同角度、光线、距离）
2. 使用 [Roboflow](https://roboflow.com) 或 LabelImg 标注
3. 按 `data/images/train` 和 `data/labels/train` 结构存放
4. 重新运行 `python train.py`

### 3. 训练参数说明（可在train.py中调整）

- `epochs=50`：先用50轮测试，效果好再增加到100~200
- `imgsz=640`：平衡速度和精度
- `batch=16`：根据显存调整（显存小可改为8）
- `patience=20`：早停机制，避免过拟合

### 4. 测试训练好的模型

训练完成后可运行：

```bash
# 测试图片
python detect.py --source data/images/val --weights runs/person_detect/weights/best.pt

# 测试摄像头（后续会改成IP摄像头）
python detect.py --source 0 --weights runs/person_detect/weights/best.pt
```

---

## 下一步计划

训练完成后，请告诉我以下信息，我将立即进行下一步：

1. 模型训练是否成功？（运行 `python train.py` 后告诉我结果）
2. 是否需要我**修改代码将YOLO集成到实时视频流中**？（推荐）
3. 之后再添加 **IP摄像头（RTSP）** 支持

---

**当前状态**：已为您准备好训练环境，`train.py` 和 `dataset.yaml` 均已优化为**person闯入检测**专用。

**请现在运行以下命令开始训练：**

```bash
python train.py
```

训练结束后回复我，我们继续集成实时检测和IP摄像头支持。
