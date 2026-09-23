import os, sys, time, ctypes, glob, re, json      # 2026-09-23 修复：原缺 time，第 57 行一跑就 NameError
from pathlib import Path

# 2026-09-23 去本地化：stems 根改为 参数 argv[1] → 环境变量 STEMS_ROOT → 同级盘 assets/radio_music_stems
_REPOS_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT = Path(os.environ.get("STEMS_ROOT") or (_REPOS_ROOT.parent / "assets" / "radio_music_stems"))
_target = Path(sys.argv[1]) if len(sys.argv) > 1 else _DEFAULT
if not _target.is_dir():
    raise SystemExit(f"[错误] stems 目录不存在：{_target}\n  用法：python _inspect_run.py [stems目录]（或设 STEMS_ROOT）")
os.chdir(_target)

# stems 子目录数
subdirs = [d for d in os.listdir('.') if os.path.isdir(d)]
print('子目录数:', len(subdirs))
full = 0
for d in subdirs:
    n = len(glob.glob(os.path.join(d, '*.wav')) + glob.glob(os.path.join(d, '*.WAV')))
    if n >= 3:
        full += 1
print('含>=3 .wav 的完整 stems 目录数:', full)

# ALL_DONE.txt
print('ALL_DONE.txt:', '存在' if os.path.exists('ALL_DONE.txt') else '不存在')

# 锁文件
lock = '.separating.lock'
if os.path.exists(lock):
    print('锁文件: 存在')
    content = open(lock, encoding='utf-8', errors='replace').read()
    print('锁内容:', repr(content))
    m = re.search(r'pid["\x27:= \t]+(\d+)', content, re.I)
    if not m:
        m = re.search(r'\b(\d{3,8})\b', content)
    if m:
        pid = int(m.group(1))
        print('PID:', pid)
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        h = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if h:
            code = ctypes.c_ulong()
            ctypes.windll.kernel32.GetExitCodeProcess(h, ctypes.byref(code))
            ctypes.windll.kernel32.CloseHandle(h)
            if code.value == 259:
                print('PID存活: True (STILL_ACTIVE)')
            else:
                print('PID存活: False (ExitCode', code.value, ')')
        else:
            err = ctypes.windll.kernel32.GetLastError()
            print('PID存活: False (OpenProcess失败, err=', err, ')')
    else:
        print('未能解析 PID')
else:
    print('锁文件: 不存在')

# batch_progress mtime
if os.path.exists('batch_progress.json'):
    print('progress mtime:', time.ctime(os.path.getmtime('batch_progress.json')))
