# Corzz Optimizer — EXE Loader (No Tkinter)
# Console-based loader with sections ("tabs") and toggles. Buildable to EXE via PyInstaller.
# Requires Windows 10/11 and Administrator privileges for most actions.

import os
import sys
import time
import shutil
import ctypes
import subprocess
import tempfile
import re
from pathlib import Path
from datetime import datetime

APP_NAME = "Corzz Optimizer Loader (CLI)"
LOG_DIR = Path(os.environ.get("ProgramData", str(Path.home()))) / "CorzzOptimizer"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_PATH = LOG_DIR / "corzz_loader.log"
STATE_PATH = LOG_DIR / "state_cli.ini"

POWER_ULTIMATE_GUID = "e9a42b02-d5df-448d-aa00-03f14749eb61"


def log(msg: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}\n"
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line)
    except Exception:
        pass


def is_admin() -> bool:
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except Exception:
        return False


def relaunch_as_admin():
    params = " ".join([f'"{arg}"' for arg in sys.argv])
    ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, params, None, 1)


def run(cmd, shell=False, timeout=120):
    log(f"RUN: {cmd}")
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, shell=shell, timeout=timeout)
        if p.stdout:
            log("STDOUT: " + p.stdout.strip())
        if p.stderr:
            log("STDERR: " + p.stderr.strip())
        return p.returncode, p.stdout, p.stderr
    except subprocess.TimeoutExpired:
        log("Timeout")
        return 1, "", "Timeout"
    except Exception as e:
        log(f"Error: {e}")
        return 1, "", str(e)

# ------------------ Power Plan ------------------

def get_active_power_scheme_guid():
    rc, out, err = run(["powercfg", "/getactivescheme"])
    if rc == 0 and out:
        m = re.search(r"GUID:\s*([a-fA-F0-9\-]{36})", out)
        if m:
            return m.group(1)
    return None


def enable_ultimate():
    rc, out, err = run(["powercfg", "/list"])
    if POWER_ULTIMATE_GUID.lower() not in (out + err).lower():
        run(["powercfg", "/duplicatescheme", POWER_ULTIMATE_GUID])
    prev = get_active_power_scheme_guid()
    if prev:
        try:
            STATE_PATH.write_text(f"previous_scheme={prev}\n", encoding="utf-8")
        except Exception:
            pass
    rc, out, err = run(["powercfg", "/setactive", POWER_ULTIMATE_GUID])
    ok = (rc == 0)
    log("Ultimate Performance " + ("enabled" if ok else "FAILED"))
    return ok


def restore_power():
    try:
        if not STATE_PATH.exists():
            return False
        prev = None
        for line in STATE_PATH.read_text(encoding="utf-8").splitlines():
            if line.startswith("previous_scheme="):
                prev = line.split("=",1)[1].strip()
        if prev:
            rc, out, err = run(["powercfg", "/setactive", prev])
            return rc == 0
    except Exception:
        pass
    return False

# ------------------ Visual Effects ------------------

def set_visual_fx_best_performance():
    try:
        import winreg
    except Exception:
        return False
    try:
        key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Explorer\VisualEffects")
        import winreg as _wg
        _wg.SetValueEx(key, "VisualFXSetting", 0, _wg.REG_DWORD, 2)
        return True
    except Exception:
        return False

# ------------------ Temp Cleaner ------------------

def size_fmt(n):
    step = 1024.0
    for u in ["B","KB","MB","GB","TB"]:
        if n < step:
            return f"{n:.1f} {u}"
        n /= step
    return f"{n:.1f} PB"


def clean_temp(include_system=True, aggressive=False, older_days=7):
    targets = [Path(os.environ.get("TEMP", tempfile.gettempdir())), Path.home()/"AppData"/"Local"/"Temp"]
    if include_system:
        targets.append(Path("C:/Windows/Temp"))
    if aggressive:
        targets.append(Path("C:/Windows/Prefetch"))
    cutoff = time.time() - older_days*86400 if older_days else None
    freed = 0
    for d in targets:
        if not d.exists():
            continue
        for root, subdirs, files in os.walk(d, topdown=False):
            for name in files:
                fp = Path(root)/name
                try:
                    if cutoff and fp.stat().st_mtime > cutoff:
                        continue
                    sz = fp.stat().st_size
                    os.chmod(fp, 0o666)
                    fp.unlink(missing_ok=True)
                    freed += sz
                except Exception:
                    continue
            for name in subdirs:
                dp = Path(root)/name
                try:
                    dp.rmdir()
                except Exception:
                    pass
    log(f"Temp cleaned: {size_fmt(freed)}")
    return freed

# ------------------ Benchmarks ------------------

def bench_disk(size_mb=50):
    test_file = Path(tempfile.gettempdir())/"corzz_bench.tmp"
    data = os.urandom(1024*1024)
    t0 = time.time()
    with open(test_file, "wb") as f:
        for _ in range(size_mb):
            f.write(data)
    wt = time.time()-t0
    t0 = time.time()
    with open(test_file, "rb") as f:
        while f.read(1024*1024):
            pass
    rt = time.time()-t0
    try:
        test_file.unlink()
    except Exception:
        pass
    return (size_mb/wt + size_mb/rt)/2.0


def bench_mem(size_mb=200):
    block = bytearray(os.urandom(1024*1024))
    blocks = [block[:] for _ in range(size_mb)]
    t0 = time.time()
    for i in range(len(blocks)-1):
        blocks[i] = blocks[i+1]
    elapsed = time.time()-t0
    return size_mb/elapsed


def bench_cpu(n=50000):
    t0 = time.time()
    count = 0
    for i in range(2, n):
        prime = True
        j = 2
        while j*j <= i:
            if i % j == 0:
                prime = False
                break
            j += 1
        if prime:
            count += 1
    elapsed = time.time()-t0
    return count/elapsed

# ------------------ Startup Items (basic) ------------------

def list_startup_items():
    try:
        import winreg
    except Exception:
        return []
    items = []
    pairs = [
        (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run"),
        (winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\Run"),
    ]
    for hive, path in pairs:
        try:
            with winreg.OpenKey(hive, path) as key:
                i = 0
                while True:
                    try:
                        name, value, _ = winreg.EnumValue(key, i)
                        items.append(("HKCU" if hive==winreg.HKEY_CURRENT_USER else "HKLM", path, name, value))
                        i += 1
                    except OSError:
                        break
        except FileNotFoundError:
            continue
    return items


def toggle_startup(name, hive_str="HKCU", disable=True):
    try:
        import winreg
    except Exception:
        return False
    hive = winreg.HKEY_CURRENT_USER if hive_str=="HKCU" else winreg.HKEY_LOCAL_MACHINE
    base = r"Software\Microsoft\Windows\CurrentVersion\Run"
    backup = base + "_Disabled_By_Corzz"
    src = backup if disable is False else base
    dst = base if disable is False else backup
    try:
        with winreg.OpenKey(hive, src) as src_key:
            value, vtype = winreg.QueryValueEx(src_key, name)
    except FileNotFoundError:
        return False
    dst_key = winreg.CreateKey(hive, dst)
    winreg.SetValueEx(dst_key, name, 0, vtype, value)
    winreg.DeleteValue(winreg.OpenKey(hive, src, 0, winreg.KEY_SET_VALUE), name)
    return True

# ------------------ Menu UI ------------------

def clear():
    os.system("cls" if os.name=="nt" else "clear")


def pause():
    input("\nPress Enter to continue…")


def header(title="Main"):
    clear()
    print(f"==== {APP_NAME} — {title} ====")
    print(f"Log: {LOG_PATH}")


def menu_main():
    while True:
        header("Home")
        print("1) Performance Tweaks")
        print("2) Temp Cleaner")
        print("3) Benchmark")
        print("4) Startup Manager")
        print("5) Power Plan")
        print("6) View Log")
        print("0) Exit")
        choice = input("\nSelect: ").strip()
        if choice == "1":
            menu_tweaks()
        elif choice == "2":
            menu_cleaner()
        elif choice == "3":
            menu_bench()
        elif choice == "4":
            menu_startup()
        elif choice == "5":
            menu_power()
        elif choice == "6":
            print(LOG_PATH.read_text(encoding="utf-8") if LOG_PATH.exists() else "(No logs)")
            pause()
        elif choice == "0":
            break


def menu_tweaks():
    while True:
        header("Performance Tweaks")
        print("1) Enable Ultimate Performance")
        print("2) Restore previous power plan")
        print("3) Set Visual Effects → Best Performance (sign out/in for full effect)")
        print("0) Back")
        c = input("Select: ").strip()
        if c == "1":
            ok = enable_ultimate()
            print("Done" if ok else "Failed")
            pause()
        elif c == "2":
            ok = restore_power()
            print("Restored" if ok else "No saved plan / failed")
            pause()
        elif c == "3":
            ok = set_visual_fx_best_performance()
            print("Applied" if ok else "Failed")
            pause()
        elif c == "0":
            return


def menu_cleaner():
    header("Temp Cleaner")
    days = input("Delete files older than how many days? [7]: ").strip() or "7"
    try:
        days_i = int(days)
    except ValueError:
        days_i = 7
    inc_sys = input("Include system temp (C:/Windows/Temp)? [Y/n]: ").strip().lower() != "n"
    aggressive = input("Aggressive (add Prefetch)? [y/N]: ").strip().lower() == "y"
    freed = clean_temp(include_system=inc_sys, aggressive=aggressive, older_days=days_i)
    print(f"Freed {size_fmt(freed)}")
    pause()


def menu_bench():
    header("Benchmark")
    print("Running quick synthetic tests…\n")
    d = bench_disk()
    m = bench_mem()
    c = bench_cpu()
    print(f"Disk I/O: {d:.2f} MB/s")
    print(f"Memory Throughput: {m:.2f} MB/s")
    print(f"CPU Perf: {c:.2f} ops/sec")
    log(f"BENCH — Disk:{d:.2f}MB/s Mem:{m:.2f}MB/s CPU:{c:.2f}ops/s")
    pause()


def menu_startup():
    while True:
        header("Startup Manager")
        items = list_startup_items()
        if not items:
            print("No startup items found or registry unavailable.")
            pause(); return
        for idx, (hive, path, name, value) in enumerate(items, 1):
            print(f"{idx:2d}) [{hive}] {name} => {value}")
        print("\nA) Disable item number …   B) Enable item number …   0) Back")
        c = input("Choice (A/B/0): ").strip().lower()
        if c == "0":
            return
        if c in ("a","b"):
            try:
                num = int(input("Item # : ").strip())
                item = items[num-1]
            except Exception:
                continue
            ok = toggle_startup(item[2], hive_str=item[0], disable=(c=="a"))
            print("OK" if ok else "Failed")
            pause()


def menu_power():
    header("Power Plan")
    cur = get_active_power_scheme_guid()
    print(f"Active scheme GUID: {cur or 'Unknown'}\n")
    print("1) Enable Ultimate Performance")
    print("2) Restore previous plan")
    print("0) Back")
    c = input("Select: ").strip()
    if c == "1":
        print("Enabling…", "OK" if enable_ultimate() else "Failed")
        pause()
    elif c == "2":
        print("Restoring…", "OK" if restore_power() else "Failed")
        pause()


def main():
    if os.name != "nt":
        print("This tool is Windows-only.")
        return
    if not is_admin():
        print("Administrator privileges are required. Relaunching as admin…")
        relaunch_as_admin()
        return
    menu_main()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nExiting…")
    except Exception as e:
        log(f"Fatal: {e}")
        raise
