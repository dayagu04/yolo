# YOLOv8 项目

## 安装

```bash
pip install -r requirements.txt
```

## 项目结构

```
yolo/
├── data/
│   ├── images/
│   │   ├── train/      # 训练图片
│   │   └── val/        # 验证图片
│   ├── labels/
│   │   ├── train/      # 训练标签 (YOLO格式 .txt)
│   │   └── val/        # 验证标签
│   └── dataset.yaml    # 数据集配置
├── runs/               # 训练/推理输出
├── train.py            # 训练脚本
├── detect.py           # 推理脚本
└── requirements.txt
```

## 使用

### 1. 准备数据

将图片放入 `data/images/train` 和 `data/images/val`，标签放入对应的 `data/labels/` 目录。

标签格式（每行一个目标）：
```
<class_id> <x_center> <y_center> <width> <height>
```
所有值归一化到 0~1。

修改 `data/dataset.yaml` 中的类别数量和名称。

### 2. 训练

```bash
python train.py
```

### 3. 推理

```bash
python detect.py --source data/images/val --weights runs/train/weights/best.pt
# 使用摄像头
python detect.py --source 0
```
