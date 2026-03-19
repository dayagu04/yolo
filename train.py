from ultralytics import YOLO


def train():
    model = YOLO('yolov8n.pt')  # 加载预训练模型

    results = model.train(
        data='data/dataset.yaml',
        epochs=100,
        imgsz=640,
        batch=16,
        project='runs',
        name='train',
        device=0,  # GPU, 改为 'cpu' 使用 CPU
    )

    return results


if __name__ == '__main__':
    train()
