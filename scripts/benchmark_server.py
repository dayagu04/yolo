#!/usr/bin/env python3
"""
服务器训练性能探针：在超参搜索前运行，压榨 GPU/数据加载潜力并写出建议。

默认用数据集子集 (fraction) + 1 个 epoch + 关闭验证，尽快得到可复用的 batch/workers/AMP 结论。
结果写入 logs/server_benchmark.json；hyperparameter_tuning.py / train.py 会自动读取（若存在）。

用法（在仓库根目录）:
  python3 scripts/benchmark_server.py
  python3 scripts/benchmark_server.py --fraction 0.05
  python3 scripts/benchmark_server.py --skip-amp   # 跳过 AMP 对比

日志: logs/benchmark_server_*.log（含 print）；Ultralytics 的 LOGGER 会双写到同一文件。
说明: Ultralytics 默认 AMP 自检会拉 yolo26n.pt，弱网下像「卡住」；本脚本已跳过该自检。
"""

from __future__ import annotations

import argparse
import gc
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

# 仓库根目录
ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

os.chdir(ROOT)

import torch
from ultralytics import YOLO


DEFAULT_DATA = "data/dataset.yaml"
OUTPUT_REL = "logs/server_benchmark.json"
BATCH_CANDIDATES = [16, 32, 48, 64, 80, 96, 112, 128, 144, 160, 192, 224, 256]
WORKER_CANDIDATES = [4, 8, 16, 32, 48, 64, 96]

# 预训练权重：放在仓库根目录可避免 Ultralytics 反复从 GitHub 下载（与数据集无关）
WEIGHTS = ROOT / "yolov8n.pt"


def yolov8n_weights() -> str:
    p = WEIGHTS
    return str(p) if p.is_file() and p.stat().st_size > 100_000 else "yolov8n.pt"


def _reset_cuda():
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
        torch.cuda.reset_peak_memory_stats()
        torch.cuda.synchronize()


def _peak_mem_mb() -> float:
    if not torch.cuda.is_available():
        return 0.0
    return torch.cuda.max_memory_allocated() / (1024**2)


def _run_short_train(
    *,
    data: str,
    batch: int,
    workers: int,
    amp: bool,
    fraction: float,
    epochs: int,
    imgsz: int,
    device: int | str,
    run_name: str,
) -> tuple[float, float]:
    """返回 (耗时秒, 峰值显存 MB)。失败则抛出异常。"""
    _reset_cuda()
    t0 = time.perf_counter()
    model = YOLO(yolov8n_weights())
    model.train(
        data=data,
        epochs=epochs,
        imgsz=imgsz,
        batch=batch,
        fraction=fraction,
        device=device,
        workers=workers,
        amp=amp,
        val=False,
        plots=False,
        save=False,
        verbose=False,
        patience=epochs,
        project="runs/benchmark",
        name=run_name,
        exist_ok=True,
        seed=42,
    )
    if torch.cuda.is_available():
        torch.cuda.synchronize()
    elapsed = time.perf_counter() - t0
    peak = _peak_mem_mb()
    return elapsed, peak


def find_max_batch(
    *,
    data: str,
    fraction: float,
    epochs: int,
    imgsz: int,
    device: int,
    workers: int,
    amp: bool,
) -> tuple[int, int | None, list[dict]]:
    """线性递增 batch 直至 OOM；返回 (最大可用 batch, 首次失败的 batch 或 None, 明细)。"""
    max_ok = 0
    first_fail: int | None = None
    rows: list[dict] = []

    for b in BATCH_CANDIDATES:
        if first_fail is not None:
            break
        run_name = f"probe_b{b}_{int(time.time())}"
        try:
            sec, peak = _run_short_train(
                data=data,
                batch=b,
                workers=workers,
                amp=amp,
                fraction=fraction,
                epochs=epochs,
                imgsz=imgsz,
                device=device,
                run_name=run_name,
            )
            max_ok = b
            rows.append({"batch": b, "ok": True, "seconds": round(sec, 2), "peak_mem_mb": round(peak, 1)})
        except RuntimeError as e:
            err = str(e).lower()
            if "out of memory" in err or "cuda" in err:
                first_fail = b
                rows.append({"batch": b, "ok": False, "error": str(e)[:200]})
            else:
                raise
        finally:
            _reset_cuda()

    if max_ok == 0:
        raise RuntimeError("连最小 batch 都无法训练，请检查 data/dataset.yaml 与 CUDA 环境。")
    return max_ok, first_fail, rows


def sweep_workers(
    *,
    data: str,
    batch: int,
    fraction: float,
    epochs: int,
    imgsz: int,
    device: int,
    amp: bool,
) -> tuple[int, dict[str, float]]:
    """在固定 batch 下扫 workers，返回 (最快对应的 workers, 全部耗时)。"""
    cpu = os.cpu_count() or 8
    timings: dict[str, float] = {}
    best_w, best_t = 4, float("inf")

    for w in WORKER_CANDIDATES:
        if w > cpu:
            continue
        run_name = f"probe_w{w}_b{batch}_{int(time.time())}"
        try:
            sec, _ = _run_short_train(
                data=data,
                batch=batch,
                workers=w,
                amp=amp,
                fraction=fraction,
                epochs=epochs,
                imgsz=imgsz,
                device=device,
                run_name=run_name,
            )
            timings[str(w)] = round(sec, 2)
            if sec < best_t:
                best_t, best_w = sec, w
        finally:
            _reset_cuda()

    return best_w, timings


def compare_amp(
    *,
    data: str,
    batch: int,
    workers: int,
    fraction: float,
    epochs: int,
    imgsz: int,
    device: int,
) -> tuple[bool, float, float]:
    """返回 (是否建议 AMP True, amp=True 秒, amp=False 秒)。"""
    t_true, _ = _run_short_train(
        data=data,
        batch=batch,
        workers=workers,
        amp=True,
        fraction=fraction,
        epochs=epochs,
        imgsz=imgsz,
        device=device,
        run_name=f"probe_amp1_{int(time.time())}",
    )
    _reset_cuda()
    t_false, _ = _run_short_train(
        data=data,
        batch=batch,
        workers=workers,
        amp=False,
        fraction=fraction,
        epochs=epochs,
        imgsz=imgsz,
        device=device,
        run_name=f"probe_amp0_{int(time.time())}",
    )
    _reset_cuda()
    return t_true <= t_false, round(t_true, 2), round(t_false, 2)


def build_batch_candidates(max_ok: int) -> list[int]:
    """为后续超参搜索生成 2～3 个代表性 batch（不超过探针得到的上限）。"""
    tiers = [48, 64, 96, 128, 160, 192]
    picked = [b for b in tiers if b <= max_ok]
    if not picked:
        return [max(8, max_ok)]
    if len(picked) >= 3:
        return picked[-3:]
    return picked


def main():
    ap = argparse.ArgumentParser(description="YOLO 训练服务器性能探针")
    ap.add_argument("--data", default=DEFAULT_DATA, help="数据集 yaml 路径")
    ap.add_argument("--fraction", type=float, default=0.03, help="训练集使用比例 (0–1)，越大越准越慢")
    ap.add_argument("--epochs", type=int, default=1, help="每个探针运行的 epoch 数")
    ap.add_argument("--imgsz", type=int, default=640)
    ap.add_argument("--output", default=OUTPUT_REL, help="JSON 输出路径（相对仓库根）")
    ap.add_argument(
        "--probe-workers",
        type=int,
        default=8,
        help="探测最大 batch 时使用的 workers（宜中等，避免 CPU 未稳）",
    )
    ap.add_argument("--skip-workers", action="store_true", help="跳过 workers 扫描")
    ap.add_argument("--skip-amp", action="store_true", help="跳过 AMP 开/关对比")
    args = ap.parse_args()

    data_path = ROOT / args.data if not os.path.isabs(args.data) else Path(args.data)
    if not data_path.is_file():
        print(f"找不到数据配置: {data_path}")
        sys.exit(1)

    try:
        data_str = str(data_path.relative_to(ROOT))
    except ValueError:
        data_str = str(data_path)

    from logger import Logger
    from ultralytics_bench_hooks import attach_ultralytics_file_log, patch_skip_amp_yolo26_download

    log = Logger("benchmark_server", log_dir="logs")
    try:
        log.info("任务: 服务器训练性能探针（短跑）；Ultralytics 详细行会写入本日志。")
        attach_ultralytics_file_log(log.log_file)
        patch_skip_amp_yolo26_download()

        if not torch.cuda.is_available():
            print("未检测到 CUDA，探针意义有限；仍将尝试 CPU（极慢）。")
            device: int | str = "cpu"
            device_name = "cpu"
        else:
            device = 0
            device_name = torch.cuda.get_device_name(0)

        print("=" * 72)
        print("服务器训练性能探针")
        print(f"设备: {device_name} | imgsz={args.imgsz} | fraction={args.fraction} | epochs/次={args.epochs}")
        print(f"数据: {data_str}")
        print(f"详细日志文件: {log.log_file}")
        print("=" * 72)

        out_path = ROOT / args.output
        out_path.parent.mkdir(parents=True, exist_ok=True)

        # 1) 最大 batch（AMP 开，贴近默认训练）
        print("\n[1/3] 探测最大 batch（AMP=True）…")
        max_ok, first_fail, batch_rows = find_max_batch(
            data=data_str,
            fraction=args.fraction,
            epochs=args.epochs,
            imgsz=args.imgsz,
            device=device,
            workers=args.probe_workers,
            amp=True,
        )
        print(f"  最大可用 batch ≈ {max_ok}" + (f"，首次 OOM batch={first_fail}" if first_fail else ""))

        # 2) workers
        best_workers = args.probe_workers
        worker_timings: dict[str, float] = {}
        if args.skip_workers:
            print("\n[2/3] 跳过 workers 扫描")
        else:
            print("\n[2/3] 在最大可用 batch 下扫描 DataLoader workers…")
            best_workers, worker_timings = sweep_workers(
                data=data_str,
                batch=max_ok,
                fraction=args.fraction,
                epochs=args.epochs,
                imgsz=args.imgsz,
                device=device,
                amp=True,
            )
            print(f"  推荐 workers = {best_workers}（本轮子集上耗时最短）")

        # 3) AMP
        amp_recommend = True
        amp_true_sec = amp_false_sec = 0.0
        if args.skip_amp:
            print("\n[3/3] 跳过 AMP 对比")
        else:
            print("\n[3/3] 对比 AMP 开/关耗时…")
            amp_recommend, amp_true_sec, amp_false_sec = compare_amp(
                data=data_str,
                batch=max_ok,
                workers=best_workers,
                fraction=args.fraction,
                epochs=args.epochs,
                imgsz=args.imgsz,
                device=device,
            )
            print(f"  建议 amp={'True' if amp_recommend else 'False'}  (True={amp_true_sec}s, False={amp_false_sec}s)")

        batch_candidates = build_batch_candidates(max_ok)
        report = {
            "created_at": datetime.now().isoformat(),
            "device_name": device_name,
            "data": data_str,
            "imgsz": args.imgsz,
            "fraction": args.fraction,
            "epochs_per_probe": args.epochs,
            "max_batch_ok": max_ok,
            "batch_first_oom": first_fail,
            "batch_probe_detail": batch_rows,
            "best_workers": best_workers,
            "worker_timings_sec": worker_timings,
            "amp_recommended": amp_recommend,
            "amp_true_seconds": amp_true_sec,
            "amp_false_seconds": amp_false_sec,
            "recommend": {
                "batch_candidates": batch_candidates,
                "workers": best_workers,
                "amp": amp_recommend,
            },
            "note": "结论基于 fraction 子集与短 epoch；全量训练前若改 imgsz/模型需重跑探针。",
        }

        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)

        print("\n" + "=" * 72)
        print(f"已写入: {out_path}")
        print(f"超参搜索建议 batch 档位: {batch_candidates} | workers={best_workers} | amp={amp_recommend}")
        print("下一步: python3 scripts/hyperparameter_tuning.py")
        print("=" * 72)
    finally:
        log.restore_stdout()


if __name__ == "__main__":
    main()
