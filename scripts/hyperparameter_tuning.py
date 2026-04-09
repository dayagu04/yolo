"""
YOLOv8 超参数随机搜索：epochs × 学习率 × batch × 优化器 × 损失权重。
数据路径与 batch/workers/AMP 等运行配置见下方 HARDWARE_PROFILE（由本机探针结果填写，不读 JSON）。
"""

from ultralytics import YOLO
import torch
import json
from pathlib import Path
import sys
from datetime import datetime
import shutil

sys.path.insert(0, str(Path(__file__).parent))
from logger import Logger

REPO_ROOT = Path(__file__).resolve().parents[1]

# ---------------------------------------------------------------------------
# 数据与硬件运行配置（与 logs/server_benchmark.json 2026-03-28 探针对齐，可手改）
# ---------------------------------------------------------------------------
HARDWARE_PROFILE = {
    "data": "data/dataset.yaml",
    "imgsz": 640,
    "max_batch_ok": 256,
    "batch_candidates": [128, 160, 192],
    "workers": 4,
    "amp": True,
}


def yolov8n_weights() -> str:
    p = REPO_ROOT / "yolov8n.pt"
    return str(p) if p.is_file() and p.stat().st_size > 100_000 else "yolov8n.pt"


def build_batch_opt_configs(batch_list):
    """由探针得到的 batch 列表构造与原先类似的 optimizer 组合。"""
    batch_list = sorted({int(b) for b in batch_list if int(b) >= 8})
    if not batch_list:
        batch_list = [64, 128]
    if len(batch_list) >= 2:
        lo, hi = batch_list[0], batch_list[-1]
    else:
        lo = hi = batch_list[0]
    configs = [
        {"batch": hi, "optimizer": "AdamW", "name_suffix": f"b{hi}_adamw"},
        {"batch": hi, "optimizer": "SGD", "name_suffix": f"b{hi}_sgd"},
        {"batch": lo, "optimizer": "AdamW", "name_suffix": f"b{lo}_adamw"},
        {"batch": lo, "optimizer": "SGD", "name_suffix": f"b{lo}_sgd"},
        {"batch": hi, "optimizer": "auto", "name_suffix": f"b{hi}_auto"},
    ]
    # 去重（lo==hi 时）
    seen = set()
    out = []
    for c in configs:
        key = (c["batch"], c["optimizer"])
        if key not in seen:
            seen.add(key)
            out.append(c)
    return out


class HyperparameterTuner:
    """快速超参数调优器 - 专注于train.py中的关键参数"""
    
    def __init__(self):
        self.results = []
        self.best_result = None
        self.best_score = 0.0
        
        # 创建专门用于记录调优全局进度的日志
        self.master_log_path = Path("logs/tuning_master_progress.log")
        self.master_log_path.parent.mkdir(parents=True, exist_ok=True)
        # 初始化清空并写入头部
        with open(self.master_log_path, 'w', encoding='utf-8') as f:
            f.write(f"=== YOLOv8 超参数搜索全局进度日志 ===\n")
            f.write(f"开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            
    def _log_master_progress(self, message):
        """记录全局进度"""
        with open(self.master_log_path, 'a', encoding='utf-8') as f:
            f.write(f"[{datetime.now().strftime('%H:%M:%S')}] {message}\n")
            print(f"[{datetime.now().strftime('%H:%M:%S')}] {message}")
        
    def generate_configs(self):
        """参数搜索空间；batch/workers/amp/data 来自 HARDWARE_PROFILE。"""
        configs = []
        hw = HARDWARE_PROFILE

        # 基础配置模板
        base_config = {
            "data": hw["data"],
            "imgsz": int(hw["imgsz"]),
            "patience": 30,
            "pretrained": True,
            "momentum": 0.937,
            "weight_decay": 0.0005,
            "warmup_epochs": 3.0,
            "amp": bool(hw["amp"]),
            "workers": int(hw["workers"]),
            "seed": 42,
        }
        self._log_master_progress(
            f"使用 HARDWARE_PROFILE: data={hw['data']}, imgsz={hw['imgsz']}, "
            f"workers={base_config['workers']}, amp={base_config['amp']}, "
            f"max_batch_ok={hw['max_batch_ok']}, batch_candidates={hw['batch_candidates']}"
        )
        
        # 1. epochs 组合 (数据集大，epoch可适当减少)
        # 6万数据跑100个epoch已经相当于小数据跑几千个了
        epochs_list = [50, 100, 150]
        
        # 2. 学习率组合 (覆盖更广范围)
        lr_configs = [
            {'lr0': 0.01, 'lrf': 0.01, 'name_suffix': 'lr01'},
            {'lr0': 0.005, 'lrf': 0.01, 'name_suffix': 'lr005'},
            {'lr0': 0.002, 'lrf': 0.01, 'name_suffix': 'lr002'}, # 为SGD准备的小学习率
            {'lr0': 0.015, 'lrf': 0.005, 'name_suffix': 'lr015'}, # 稍大的学习率
        ]
        
        # 3. Batch size & Optimizer（档位来自 HARDWARE_PROFILE["batch_candidates"]）
        batch_opt_configs = build_batch_opt_configs(hw["batch_candidates"])
        
        # 4. 损失权重组合 (全面测试各种侧重点)
        loss_configs = [
            {'box': 7.5, 'cls': 0.5, 'name_suffix': 'loss_default'}, # 官方默认
            {'box': 5.0, 'cls': 0.8, 'name_suffix': 'loss_cls_focus'}, # 侧重分类
            {'box': 9.0, 'cls': 0.3, 'name_suffix': 'loss_box_focus'}, # 侧重回归
            {'box': 6.5, 'cls': 0.65, 'name_suffix': 'loss_balanced'}, # 均衡
        ]
        
        # 彻底版：epochs × lr × batch × loss 全面组合
        config_id = 1
        total_expected = len(epochs_list) * len(lr_configs) * len(batch_opt_configs) * len(loss_configs)
        print(f"正在生成参数组合...")
        print(f"epochs={epochs_list}, batch/optimizer 组合数={len(batch_opt_configs)}, 展开后约 {total_expected} 组（过滤后更少）")

        for epochs in epochs_list:
            for lr_cfg in lr_configs:
                for bo_cfg in batch_opt_configs:
                    for loss_cfg in loss_configs:
                        # 排除不合理的组合以节省时间
                        # 比如 SGD 配过大的学习率容易飞，AdamW 配极小的学习率学得太慢
                        if bo_cfg['optimizer'] == 'SGD' and lr_cfg['lr0'] > 0.01:
                            continue
                        if bo_cfg['optimizer'] == 'AdamW' and lr_cfg['lr0'] < 0.005:
                            continue
                            
                        cfg = base_config.copy()
                        cfg['epochs'] = epochs
                        cfg.update(lr_cfg)
                        cfg.update(bo_cfg)
                        cfg.update(loss_cfg)
                        cfg['data'] = base_config['data']
                        cfg['imgsz'] = base_config['imgsz']
                        cfg['workers'] = base_config['workers']
                        cfg['amp'] = base_config['amp']
                        cfg['name'] = f'ep{epochs}_{lr_cfg["name_suffix"]}_{bo_cfg["name_suffix"]}_{loss_cfg["name_suffix"]}'
                        configs.append(cfg)
                        config_id += 1

        import random
        random.seed(42) # 固定种子以保证每次抽样相同
        
        # 服务器算力充足，为了找到全局最优解，扩大随机测试数量
        # 测试 30 组配置（大约需要跑 3-5 天，A30跑得很快）
        test_samples = 30
        if len(configs) > test_samples:
            configs = random.sample(configs, test_samples)
            
        print(f"\n✅ 最终生成并抽取了 {len(configs)} 组有效配置进行测试！")
        
        self._log_master_progress(f"本次随机抽取了 {len(configs)} 组超参数组合。")
        self._log_master_progress(
            "耗时与数据集规模、batch、早停有关；探针仅测子集速度，全量请以实测为准。"
        )
        self._log_master_progress(
            f"==> 本批共 {len(configs)} 组配置；若单组约 2–8 小时，总计约 {2 * len(configs)}–{8 * len(configs)} 小时量级。"
        )
        self._log_master_progress(f"（建议：随时可以手动中断，中断时会保留当前已经测试出的最佳配置。）\n")
        
        return configs
    
    def run_training(self, config, device):
        """运行单次训练"""
        config_name = config['name']
        log = Logger(f"tuning_{config_name}", log_dir="logs/tuning")
        
        log.section(f"超参数调优 - {config_name}")
        log.info(f"参数: epochs={config['epochs']}, batch={config.get('batch', 16)}, "
                f"lr0={config.get('lr0', 0.01)}, optimizer={config.get('optimizer', 'AdamW')}")
        
        model = YOLO(yolov8n_weights())
        
        start_time = datetime.now()
        
        try:
            results = model.train(
                data=config.get('data', HARDWARE_PROFILE['data']),
                epochs=config['epochs'],
                imgsz=config.get('imgsz', HARDWARE_PROFILE['imgsz']),
                batch=config.get('batch', 16),
                patience=config.get('patience', 50),
                project='runs/tuning',
                name=config_name,
                device=device,
                pretrained=config.get('pretrained', True),
                optimizer=config.get('optimizer', 'AdamW'),
                lr0=config.get('lr0', 0.01),
                lrf=config.get('lrf', 0.01),
                momentum=config.get('momentum', 0.937),
                weight_decay=config.get('weight_decay', 0.0005),
                warmup_epochs=config.get('warmup_epochs', 5.0),
                amp=config.get('amp', False),
                save=True,
                save_period=20,
                verbose=False,   # 减少输出噪声
                plots=False,     # 关闭绘图，进一步节省显存
                workers=int(config.get('workers', 8)),
                seed=config.get('seed', 42),
                box=config.get('box', 7.5),
                cls=config.get('cls', 0.5),
                dfl=config.get('dfl', 1.5),
            )
            
            duration = (datetime.now() - start_time).total_seconds() / 3600.0
            
            # 提取指标
            metrics = {}
            if hasattr(results, 'results_dict'):
                rd = results.results_dict
                metrics = {
                    'mAP50': rd.get('metrics/mAP50(B)', 0.0),
                    'mAP50-95': rd.get('metrics/mAP50-95(B)', 0.0),
                    'precision': rd.get('metrics/precision(B)', 0.0),
                    'recall': rd.get('metrics/recall(B)', 0.0),
                }
            
            # 计算综合得分 (mAP50权重更高，同时考虑recall)
            score = (metrics.get('mAP50', 0) * 0.55 +
                    metrics.get('mAP50-95', 0) * 0.3 +
                    metrics.get('recall', 0) * 0.15)
            
            result = {
                'config_name': config_name,
                'config': config,
                'metrics': metrics,
                'score': score,
                'duration_hours': round(duration, 2),
                'success': True,
                'model_path': f"runs/tuning/{config_name}/weights/best.pt"
            }
            
            log.info(f"训练完成! mAP50={metrics.get('mAP50', 0):.4f} | 得分={score:.4f}")
            return result
            
        except Exception as e:
            log.error(f"训练失败: {str(e)}")
            return {
                'config_name': config_name,
                'success': False,
                'error': str(e)
            }
    
    def run(self):
        """运行调优流程"""
        print("=" * 80)
        print("YOLOv8 大规模超参数搜索 (大数据集定制版)")
        print("=" * 80)
        print("目标: 全面搜索最佳参数组合，覆盖不同的 epochs 和配置")
        print("重点参数: lr0, lrf, batch, optimizer, box, cls")
        print("本次将测试大量配置，时间较长，请耐心等待...")
        print("=" * 80)
        
        # 检测设备
        if torch.cuda.is_available():
            device = 0
            print(f"使用GPU: {torch.cuda.get_device_name(0)}")
        else:
            device = 'cpu'
            print("警告: 使用CPU训练会很慢")
        
        configs = self.generate_configs()
        total_configs = len(configs)
        print(f"\n将测试 {total_configs} 组参数组合...")
        
        for i, config in enumerate(configs, 1):
            self._log_master_progress(f"---")
            self._log_master_progress(f"即将开始测试第 {i}/{total_configs} 组配置: {config['name']}")
            self._log_master_progress(f"参数详情: epochs={config['epochs']}, batch={config.get('batch', 16)}, lr0={config.get('lr0', 0.01)}, optimizer={config.get('optimizer', 'AdamW')}, box={config.get('box', 7.5)}, cls={config.get('cls', 0.5)}")
            
            result = self.run_training(config, device)
            self.results.append(result)
            
            if result.get('success'):
                m = result['metrics']
                score = result['score']
                duration = result['duration_hours']
                
                log_msg = (f"✅ [{i}/{total_configs}] 完成 '{config['name']}'! "
                           f"耗时: {duration:.2f}小时. "
                           f"效果: mAP50={m.get('mAP50', 0):.4f}, mAP={m.get('mAP50-95', 0):.4f}, Score={score:.4f}")
                
                if score > self.best_score:
                    self.best_score = score
                    self.best_result = result
                    log_msg += " ⭐ 当前最佳配置！"
                    
                self._log_master_progress(log_msg)
            else:
                self._log_master_progress(f"❌ [{i}/{total_configs}] 失败 '{config['name']}': {result.get('error', '未知错误')}")
                
            # 每次跑完一组，立刻保存中间结果，防止意外中断
            self._save_results()
        
        self._print_final_summary()
        self._save_results()
        
        if self.best_result:
            self._copy_best_model()
        
        return self.best_result
    
    def _print_final_summary(self):
        """打印最终总结"""
        successful = [r for r in self.results if r.get('success', False)]
        
        print("\n" + "="*80)
        print("调优完成!")
        print("="*80)
        
        if not successful:
            print("没有成功的训练结果")
            return
            
        # 排序
        sorted_results = sorted(successful, key=lambda x: x['score'], reverse=True)
        
        print(f"\nTop 3 最佳配置:")
        print("-" * 70)
        print(f"{'排名':<4} {'配置名':<25} {'mAP50':<8} {'mAP':<8} {'Score':<8} {'时长(h)':<8}")
        print("-" * 70)
        
        for rank, res in enumerate(sorted_results[:3], 1):
            m = res['metrics']
            print(f"{rank:<4} {res['config_name']:<25} {m.get('mAP50',0):<8.4f} "
                  f"{m.get('mAP50-95',0):<8.4f} {res['score']:<8.4f} {res['duration_hours']:<8}")
        
        best = sorted_results[0]
        print("\n" + "="*60)
        print(f"推荐使用的最佳配置: {best['config_name']}")
        print("="*60)
        print(f"mAP50: {best['metrics'].get('mAP50', 0):.4f}")
        print(f"mAP50-95: {best['metrics'].get('mAP50-95', 0):.4f}")
        print(f"模型路径: {best['model_path']}")
        print("\n你可以将这些参数更新到 scripts/train.py 中继续训练。")
    
    def _save_results(self):
        """保存结果到JSON"""
        output_path = Path("logs/tuning_results.json")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        summary = {
            'timestamp': datetime.now().isoformat(),
            'total_configs': len(self.results),
            'successful': len([r for r in self.results if r.get('success')]),
            'best_config': self.best_result,
            'all_results': self.results
        }
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)
        
        print(f"\n详细结果已保存至: {output_path}")
    
    def _copy_best_model(self):
        """复制最佳模型到方便位置"""
        if not self.best_result:
            return
            
        best_path = Path(self.best_result['model_path'])
        target_path = Path("best_model.pt")
        
        if best_path.exists():
            shutil.copy2(best_path, target_path)
            print(f"\n最佳模型已复制到: {target_path}")
            print("使用方法: from ultralytics import YOLO; model = YOLO('best_model.pt')")


def main():
    tuner = HyperparameterTuner()
    try:
        tuner.run()
    except KeyboardInterrupt:
        print("\n\n用户中断了调优过程")
    except Exception as e:
        print(f"\n发生错误: {e}")


if __name__ == '__main__':
    main()
