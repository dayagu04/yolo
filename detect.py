import argparse
from ultralytics import YOLO


def detect(source, weights='runs/train/weights/best.pt', conf=0.25, save=True):
    model = YOLO(weights)

    results = model.predict(
        source=source,
        conf=conf,
        save=save,
        project='runs',
        name='detect',
    )

    return results


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=str, required=True, help='图片/视频路径或摄像头 (0)')
    parser.add_argument('--weights', type=str, default='runs/train/weights/best.pt')
    parser.add_argument('--conf', type=float, default=0.25)
    parser.add_argument('--no-save', action='store_true')
    args = parser.parse_args()

    detect(args.source, args.weights, args.conf, not args.no_save)
