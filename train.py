from ultralytics import YOLO


def train():
    # 加载预训练的YOLOv8n模型（小模型，适合快速训练）
    model = YOLO('yolov8n.pt')
    
    print("开始训练person检测模型...")
    print("使用公开数据集或自有数据集进行训练")
    
    results = model.train(
        data='data/dataset.yaml',   # 数据集配置文件
        epochs=50,                  # 建议先用50个epoch测试，后面可增加到100+
        imgsz=640,                  # 输入图像大小
        batch=16,
        patience=20,                # 早停策略
        project='runs',
        name='person_detect',       # 训练结果保存在 runs/person_detect
        device=0,                   # 使用GPU，改为'cpu'则使用CPU
        pretrained=True,
        optimizer='auto',
        lr0=0.01,                   # 初始学习率
        lrf=0.01,
    )
    
    print("训练完成！最佳模型保存在: runs/person_detect/weights/best.pt")
    return results


if __name__ == '__main__':
    train()
