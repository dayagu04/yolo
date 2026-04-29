"""
Prometheus 指标模块
暴露 /metrics 端点，提供系统运行指标
"""
import time
import psutil
from typing import Optional


def collect_metrics(cameras: dict, db_manager=None, redis_stats=None, start_ts: float = 0) -> str:
    """收集系统指标，返回 Prometheus 文本格式"""
    lines = []
    now = time.time()

    # ── 摄像头指标 ──
    lines.append("# HELP safecam_camera_fps Camera frame rate")
    lines.append("# TYPE safecam_camera_fps gauge")
    for cid, cam in cameras.items():
        lines.append(f'safecam_camera_fps{{camera_id="{cid}"}} {cam._fps:.2f}')

    lines.append("# HELP safecam_camera_connected Camera connection status (1=connected)")
    lines.append("# TYPE safecam_camera_connected gauge")
    for cid, cam in cameras.items():
        lines.append(f'safecam_camera_connected{{camera_id="{cid}"}} {1 if cam.connected else 0}')

    lines.append("# HELP safecam_camera_active_tracks Active person tracks per camera")
    lines.append("# TYPE safecam_camera_active_tracks gauge")
    for cid, cam in cameras.items():
        lines.append(f'safecam_camera_active_tracks{{camera_id="{cid}"}} {cam.tracker.active_count}')

    lines.append("# HELP safecam_camera_alert_total Total alerts per camera")
    lines.append("# TYPE safecam_camera_alert_total counter")
    for cid, cam in cameras.items():
        lines.append(f'safecam_camera_alert_total{{camera_id="{cid}"}} {cam._alert_total}')

    lines.append("# HELP safecam_camera_reconnect_attempts Camera reconnection attempts")
    lines.append("# TYPE safecam_camera_reconnect_attempts gauge")
    for cid, cam in cameras.items():
        lines.append(f'safecam_camera_reconnect_attempts{{camera_id="{cid}"}} {cam._reconnect_attempts}')

    # ── 系统指标 ──
    lines.append("# HELP safecam_uptime_seconds Server uptime in seconds")
    lines.append("# TYPE safecam_uptime_seconds gauge")
    lines.append(f"safecam_uptime_seconds {int(now - start_ts)}")

    lines.append("# HELP safecam_ws_clients Connected WebSocket clients")
    lines.append("# TYPE safecam_ws_clients gauge")
    # ws_clients 由 main.py 传入

    # ── 系统资源 ──
    try:
        cpu_percent = psutil.cpu_percent(interval=None)
        mem = psutil.virtual_memory()

        lines.append("# HELP safecam_cpu_usage_percent CPU usage percentage")
        lines.append("# TYPE safecam_cpu_usage_percent gauge")
        lines.append(f"safecam_cpu_usage_percent {cpu_percent}")

        lines.append("# HELP safecam_memory_usage_bytes Memory usage in bytes")
        lines.append("# TYPE safecam_memory_usage_bytes gauge")
        lines.append(f"safecam_memory_usage_bytes {mem.used}")

        lines.append("# HELP safecam_memory_total_bytes Total memory in bytes")
        lines.append("# TYPE safecam_memory_total_bytes gauge")
        lines.append(f"safecam_memory_total_bytes {mem.total}")

        lines.append("# HELP safecam_memory_usage_percent Memory usage percentage")
        lines.append("# TYPE safecam_memory_usage_percent gauge")
        lines.append(f"safecam_memory_usage_percent {mem.percent}")
    except Exception:
        pass

    # ── GPU 指标（可选）──
    try:
        import torch
        if torch.cuda.is_available():
            gpu_mem = torch.cuda.memory_allocated()
            gpu_mem_total = torch.cuda.get_device_properties(0).total_mem
            lines.append("# HELP safecam_gpu_memory_usage_bytes GPU memory usage in bytes")
            lines.append("# TYPE safecam_gpu_memory_usage_bytes gauge")
            lines.append(f"safecam_gpu_memory_usage_bytes {gpu_mem}")
            lines.append("# HELP safecam_gpu_memory_total_bytes Total GPU memory in bytes")
            lines.append("# TYPE safecam_gpu_memory_total_bytes gauge")
            lines.append(f"safecam_gpu_memory_total_bytes {gpu_mem_total}")
    except Exception:
        pass

    return "\n".join(lines) + "\n"
