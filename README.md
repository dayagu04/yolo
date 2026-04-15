# 智能视频监控（YOLOv8 + 实时流）

## 目标

- 阶段 1：单路实时视频流到网页/App（已完成）
- 阶段 2：YOLO 检测「人」并告警（进行中）
- 阶段 3：IP 摄像头与多路拼接

## 目录说明

```
yolo/
├── scripts/           # 训练与调参
├── data/              # 数据与 dataset.yaml（仅本地，不入 Git）
├── logs/              # 日志与探针/调参结果 JSON
├── runs/              # Ultralytics 训练输出
├── server/            # 实时流服务
├── app/               # 前端
└── README.md
```

## 依赖

```bash
pip install -r requirements.txt
```

## 训练与最佳配置（推荐顺序）

在仓库根目录执行。

1. **性能探针**（子集 + 1 epoch，测最大 batch、workers、AMP）

   ```bash
   python3 scripts/benchmark_server.py
   ```

   输出 `logs/server_benchmark.json`；`train.py` 可自动读取。超参搜索的 batch/workers/数据路径写在 `scripts/hyperparameter_tuning.py` 的 `HARDWARE_PROFILE` 中，请与探针结果对齐后手改。

2. **超参数搜索**（随机抽样多组配置，按验证指标打分）

   ```bash
   python3 scripts/hyperparameter_tuning.py
   ```

   结果见 `logs/tuning_results.json`；可按最佳配置回写 `scripts/train.py` 中的学习率、优化器、box/cls 等。

3. **正式训练**

   ```bash
   python3 scripts/train.py
   ```

   若存在 `server_benchmark.json`，会使用其中的 `batch` / `workers` / `amp`；否则使用脚本内保守默认。

## 日志

训练日志在 `logs/`，文件名含时间戳。Linux 下可：`ls logs/`、`tail -f logs/*.log`。

## 后续

集成检测到实时流、IP 摄像头与多路拼接。
