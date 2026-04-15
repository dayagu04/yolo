import cv2
from ultralytics import YOLO

def main():
    # 1. 加载训练好的“模型”
    # 注意路径：在 scripts 目录下运行，模型在上一级的 models 目录里
    model_path = '../models/person_best.pt' 
    print(f"正在加载模型: {model_path}...")
    model = YOLO(model_path)
    
    # 2. 获取摄像头数据 
    # 0 代表系统默认的第一个摄像头（笔记本自带摄像头）
    # 如果外接了USB摄像头，可以尝试改成 1 或 2
    cap = cv2.VideoCapture(0)
    
    if not cap.isOpened():
        print("错误：无法打开摄像头！")
        return

    print("摄像头已开启，按 'q' 键退出...")

    # 3. 开启死循环，不断获取每一帧画面
    while True:
        # ret 是一个布尔值，代表是否成功读取；frame 就是那一瞬间的图像矩阵数据
        ret, frame = cap.read()
        
        if not ret:
            print("无法获取画面...")
            break
            
        # 4. 把画面喂给 YOLO 进行推理
        # verbose=False 可以关掉终端里一堆啰嗦的打印信息
        results = model(frame, verbose=False)
        
        # 5. 把检测结果（框框）画回画面上
        # results[0].plot() 会返回一张画好了红框和置信度的新图片
        annotated_frame = results[0].plot()
        
        # --- 告警逻辑雏形 ---
        # 如果检测到了人，我们在终端打印一下
        if len(results[0].boxes) > 0:
            print(f"🚨 警告：画面中检测到 {len(results[0].boxes)} 个人！")

        # 6. 显示处理后的画面
        cv2.imshow("YOLOv8 Real-time Detection", annotated_frame)
        
        # 7. 监听键盘，如果按下小写 'q' 键，就退出循环
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    # 8. 打扫战场，释放资源
    cap.release()
    cv2.destroyAllWindows()

if __name__ == '__main__':
    main()