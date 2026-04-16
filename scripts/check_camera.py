"""
摄像头占用检测与释放工具
用法:
  python scripts/check_camera.py          # 检测摄像头 0
  python scripts/check_camera.py 1        # 检测摄像头 1
  python scripts/check_camera.py --kill   # 终止所有可疑占用进程后再检测
"""
import cv2
import sys
import os
import subprocess
import ctypes

# Windows GBK 终端兼容
if sys.stdout.encoding and sys.stdout.encoding.lower() in ("gbk", "cp936", "gb2312"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


# ------------------------------------------------------------------ #
#  工具函数
# ------------------------------------------------------------------ #

def is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def _ps(cmd: str, timeout: int = 10) -> str:
    r = subprocess.run(
        ["powershell", "-NoProfile", "-Command", cmd],
        capture_output=True, text=True, timeout=timeout,
    )
    return r.stdout.strip()


def _taskkill(pid: int) -> bool:
    r = subprocess.run(
        ["cmd", "/c", f"taskkill /F /PID {pid}"],
        capture_output=True, text=True,
    )
    if r.returncode == 0:
        print(f"    ✓ 已终止 PID {pid}")
        return True
    print(f"    ✗ 无法终止 PID {pid}: {(r.stderr or r.stdout).strip()}")
    return False


# ------------------------------------------------------------------ #
#  摄像头检测
# ------------------------------------------------------------------ #

def check_camera(camera_id: int = 0) -> bool:
    """用 DSHOW 后端尝试读取一帧，返回是否成功"""
    print(f"\n[1] OpenCV 摄像头检测 (camera_id={camera_id}, backend=DSHOW)")
    cap = cv2.VideoCapture(camera_id, cv2.CAP_DSHOW)
    if not cap.isOpened():
        print(f"    ✗ 无法打开摄像头 {camera_id}（未找到设备或已被独占）")
        cap.release()
        return False

    ret, frame = cap.read()
    cap.release()

    if not ret or frame is None:
        print(f"    ✗ 摄像头已打开，但读帧失败（可能被独占）")
        return False

    h, w = frame.shape[:2]
    print(f"    ✓ 摄像头正常  分辨率={w}x{h}")
    return True


# ------------------------------------------------------------------ #
#  进程扫描
# ------------------------------------------------------------------ #

def scan_suspect_processes():
    """扫描可能占用摄像头的进程"""
    print("\n[2] 扫描占用摄像头的可疑进程")
    suspects = [
        "Teams", "Zoom", "obs", "obs64", "obs32",
        "chrome", "msedge", "firefox", "brave",
        "skype", "discord", "lync",
        "CameraApp", "WindowsCamera",
        "python", "pythonw",
    ]

    out = _ps(
        "Get-Process | Select-Object Id, ProcessName, Path | Format-Table -AutoSize"
    )
    found = []
    for line in out.splitlines():
        low = line.lower()
        for name in suspects:
            if name.lower() in low:
                found.append(line.strip())
                break

    if found:
        print(f"    {'PID':<8} {'进程名':<20} 路径")
        print(f"    {'-'*8} {'-'*20} {'-'*30}")
        for f in found:
            print(f"    {f}")
    else:
        print("    未发现常见占用进程")

    return found


def scan_python_processes():
    """列出所有 Python 进程（通常是残留的 main.py）"""
    print("\n[3] Python 进程列表（旧实例可能占用摄像头）")
    out = _ps(
        "Get-Process python,pythonw -ErrorAction SilentlyContinue | "
        "Select-Object Id, ProcessName, StartTime, CPU | Format-Table -AutoSize"
    )
    if out:
        print(out)
    else:
        print("    没有运行中的 Python 进程")
    return out


def check_port(port: int = 8000):
    """检查端口占用"""
    print(f"\n[4] 端口 {port} 占用情况")
    out = _ps(f"netstat -ano | Select-String ':{port}\\s'")
    if not out:
        print(f"    ✓ 端口 {port} 空闲")
        return

    pids_shown = set()
    for line in out.splitlines():
        parts = line.split()
        if not parts:
            continue
        print(f"    {line.strip()}")
        pid_str = parts[-1] if parts else None
        if pid_str and pid_str.isdigit() and pid_str not in pids_shown:
            pids_shown.add(pid_str)
            proc = _ps(
                f"Get-Process -Id {pid_str} -ErrorAction SilentlyContinue | "
                f"Select-Object Id, ProcessName | Format-Table -AutoSize"
            )
            if proc:
                for l in proc.splitlines():
                    if l.strip() and not l.startswith("Id") and not l.startswith("-"):
                        print(f"      -> 进程: {l.strip()}")


# ------------------------------------------------------------------ #
#  终止操作
# ------------------------------------------------------------------ #

def kill_python_servers(confirm: bool = True):
    """终止所有 Python 进程（排除自身）"""
    current_pid = os.getpid()
    out = _ps(
        "Get-Process python,pythonw -ErrorAction SilentlyContinue | "
        "Select-Object Id, ProcessName | Format-Table -AutoSize"
    )
    pids = []
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0].isdigit():
            pid = int(parts[0])
            if pid != current_pid:
                pids.append((pid, parts[1]))

    if not pids:
        print("    没有其他 Python 进程")
        return

    print(f"    找到 {len(pids)} 个 Python 进程:")
    for pid, name in pids:
        print(f"      PID {pid}  {name}")

    if confirm:
        ans = input("    确认全部终止? [y/N] ").strip().lower()
        if ans != "y":
            print("    已取消")
            return

    for pid, _ in pids:
        _taskkill(pid)


def kill_pid_interactive(pid_str: str):
    if pid_str.isdigit():
        _taskkill(int(pid_str))
    else:
        print("    无效 PID")


# ------------------------------------------------------------------ #
#  主流程
# ------------------------------------------------------------------ #

def main():
    force_kill = "--kill" in sys.argv
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    camera_id = int(args[0]) if args else 0

    print("=" * 60)
    print("  摄像头占用检测工具")
    print("=" * 60)
    if not is_admin():
        print("  提示：以管理员身份运行可获得完整进程信息")

    # 若带 --kill 参数，先杀掉旧 Python 进程
    if force_kill:
        print("\n[--kill] 强制终止所有 Python 进程...")
        kill_python_servers(confirm=False)

    # 检测摄像头
    ok = check_camera(camera_id)

    # 进程 & 端口扫描
    scan_suspect_processes()
    scan_python_processes()
    check_port(8000)

    print("\n" + "=" * 60)
    if ok:
        print("  结论: 摄像头可用，可以正常启动服务")
        print("  启动: python backend/main.py")
    else:
        print("  结论: 摄像头不可用\n")
        print("  选项:")
        print("  1) 终止所有 Python 进程（清理残留 main.py）")
        print("  2) 手动输入 PID 终止")
        print("  3) 退出")
        choice = input("  请选择 [1/2/3]: ").strip()
        if choice == "1":
            kill_python_servers()
            print("\n  重新检测摄像头...")
            check_camera(camera_id)
        elif choice == "2":
            pid = input("  输入 PID: ").strip()
            kill_pid_interactive(pid)
            print("\n  重新检测摄像头...")
            check_camera(camera_id)
    print("=" * 60)


if __name__ == "__main__":
    main()
