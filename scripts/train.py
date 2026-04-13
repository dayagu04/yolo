"""
YOLOv8 Person检测模型训练
"""

from ultralytics import YOLO
import torch
from pathlib import Path
import sys
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))
from logger import Logger


class TrainingCallback:
    """训练回调：记录每个epoch进度"""
    
    def __init__(self, logger):
        self.logger = logger
        self.epoch_start = None
        
    def on_train_epoch_start(self, trainer):
        """Epoch开始"""
        self.epoch_start = datetime.now()
        epoch = trainer.epoch + 1
        total = trainer.epochs
        self.logger.info(f"[Epoch {epoch}/{total}] 开始...")
        
    def on_fit_epoch_end(self, trainer):
        """Epoch结束（含验证）"""
        epoch = trainer.epoch + 1
        total = trainer.epochs
        
        # 计算用时
        elapsed = datetime.now() - self.epoch_start if self.epoch_start else None
        time_str = f"{elapsed.seconds//60}m{elapsed.seconds%60}s" if elapsed else "?"
        
        # 获取指标
        metrics = trainer.metrics
        if metrics:
            # 关键指标
            items = []
            for k in ['mAP50', 'mAP50-95', 'precision', 'recall']:
                if k in metrics and isinstance(metrics[k], (int, float)):
                    items.append(f"{k}={metrics[k]:.3f}")
            metric_str = ", ".join(items) if items else "无"
            self.logger.info(f"[Epoch {epoch}/{total}] 完成 ({time_str}) - {metric_str}")
        else:
            self.logger.info(f"[Epoch {epoch}/{total}] 完成 ({time_str})")


def train():
    """训练模型"""
    log = Logger("person_training", log_dir="logs")
    
    log.section("Person检测模型训练")
    log.info("数据集: 7937张 (0.8:0.2划分)")
    log.info("Epochs: 150 | Batch: 8 | 图像尺寸: 640")
    
    # 检查GPU
    if torch.cuda.is_available():
        device = 0
        log.info(f"GPU: {torch.cuda.get_device_name(0)}")
    else:
        device = 'cpu'
        log.warning("使用CPU")
    
    # 加载模型
    model_path = 'yolov8n.pt'
    if Path(model_path).exists():
        model = YOLO(model_path)
        log.info(f"模型: {model_path}")
    else:
        model = YOLO('yolov8n.pt')
    
    log.separator("-")
    log.info("开始训练...")
    log.separator("-")
    
    # 创建回调
    callback = TrainingCallback(log)

    # 添加回调到模型
    model.add_callback('on_train_epoch_start', callback.on_train_epoch_start)
    model.add_callback('on_fit_epoch_end', callback.on_fit_epoch_end)

    # 训练
    start_time = datetime.now()

    try:
        results = model.train(
            data='data/dataset.yaml',
            epochs=150,
            imgsz=640,
            batch=32,
            patience=50,
            project='runs',
            name='person_large_dataset',
            device=device,
            pretrained=True,
            optimizer='AdamW',
            lr0=0.01,
            lrf=0.01,
            momentum=0.937,
            weight_decay=0.0005,
            warmup_epochs=5.0,
            amp=False,
            save=True,
            save_period=20,
            verbose=True,
            plots=True,
            workers=4,
            seed=42,
            box=7.5,
            cls=0.5,
            dfl=1.5
        )
        
        # 训练完成
        log.section("训练完成")
        log.log_elapsed_time()
        
        best_model = "runs/person_large_dataset/weights/best.pt"
        log.info(f"最佳模型: {best_model}")
        
        if results and hasattr(results, 'results_dict'):
            log.info("最终指标:")
            for k, v in results.results_dict.items():
                if isinstance(v, (int, float)):
                    log.info(f"  {k}: {v:.4f}")
        
        log.separator("-")
        log.info(f"日志: {log.get_log_file().name}")
        
        return results
        
    except Exception as e:
        log.error(f"训练失败: {e}")
        raise


if __name__ == '__main__':
    train()
