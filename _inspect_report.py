# -*- coding: utf-8 -*-
"""只读巡检脚本：统计音乐、进度、stems、锁与进程状态。不写任何文件、不删任何文件。"""
import os, json, sys, glob, time, ctypes

# 2026-09-23 去本地化：源/输出根按 环境变量 → 同级仓/同级盘 推导
# （原路径均已失效）
from pathlib import Path as _Path
_REPOS_ROOT = _Path(__file__).resolve().parent.parent          # …/repos
_ASSETS_ROOT = _REPOS_ROOT.parent / "assets"                  # …/assets
RADIO_MUSIC = _Path(os.environ.get("RADIO_MUSIC_ROOT") or (_REPOS_ROOT / "private-radio-stations" / "apps" / "audio" / "music"))
RADIO_STEMS = _Path(os.environ.get("STEMS_ROOT") or (_ASSETS_ROOT / "radio_music_stems"))
CSMUSIC = _Path(os.environ.get("CSMUSIC_ROOT") or (_REPOS_ROOT.parent / "csmusic"))
CSMUSIC_STEMS = _Path(os.environ.get("CSMUSIC_STEMS_ROOT") or (_REPOS_ROOT.parent / "csmusic_stems"))
MUSIC_DIR = str(RADIO_MUSIC)
OUT_DIR   = str(RADIO_STEMS)
PROGRESS  = os.path.join(OUT_DIR, "batch_progress.json")
ALL_DONE  = os.path.join(OUT_DIR, "ALL_DONE.txt")
LOCK      = os.path.join(OUT_DIR, ".separating.lock")

EXT = (".mp3", ".flac", ".wav", ".m4a", ".ogg")
out = []

def p(s=""):
    out.append(s)

# 1. 音乐总数
total = 0
ext_count = {}
try:
    for root, dirs, files in os.walk(MUSIC_DIR):
        for f in files:
            e = os.path.splitext(f)[1].lower()
            if e in EXT:
                total += 1
                ext_count[e] = ext_count.get(e, 0) + 1
except Exception as ex:
    p("[音乐统计异常] %s" % ex)
p("音乐总数: %d" % total)
p("  分格式: %s" % json.dumps(ext_count, ensure_ascii=False))

# 2. progress.json
status_dist = {}
failed_names = []
try:
    with open(PROGRESS, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    # data 可能是 dict 或 list
    records = []
    if isinstance(data, dict):
        # 常见结构: {"songs": {...}} 或 {"progress": {...}}
        for k in ("songs", "progress", "items"):
            if k in data and isinstance(data[k], dict):
                records = list(data[k].values())
                break
            if k in data and isinstance(data[k], list):
                records = data[k]
                break
        if not records and "done" in data:
            records = data  # 可能是扁平 dict
    elif isinstance(data, list):
        records = data
    for r in records:
        if isinstance(r, dict):
            st = r.get("status", r.get("state", "unknown"))
        else:
            st = "unknown"
        status_dist[st] = status_dist.get(st, 0) + 1
        if st == "failed":
            failed_names.append(r.get("song_name", r.get("name", "?")) if isinstance(r, dict) else "?")
    p("progress 记录数: %d" % len(records))
    p("status 分布: %s" % json.dumps(status_dist, ensure_ascii=False))
    p("failed 数量: %d" % len(failed_names))
    for n in failed_names:
        p("  [failed] %s" % n)
except Exception as ex:
    p("[progress 读取异常] %s" % ex)

# 3. stems 子目录 & 完整目录
subdirs = 0
complete = 0
try:
    for name in os.listdir(OUT_DIR):
        fp = os.path.join(OUT_DIR, name)
        if os.path.isdir(fp):
            subdirs += 1
            wavs = [x for x in os.listdir(fp) if x.lower().endswith(".wav")]
            if len(wavs) >= 3:
                complete += 1
    p("stems 子目录数: %d" % subdirs)
    p(">=3 .wav 完整目录数: %d" % complete)
except Exception as ex:
    p("[stems 统计异常] %s" % ex)

# 4. ALL_DONE.txt
p("ALL_DONE.txt 存在: %s" % ("是" if os.path.exists(ALL_DONE) else "否"))

# 5. 锁
lock_exists = os.path.exists(LOCK)
p("锁 .separating.lock 存在: %s" % ("是" if lock_exists else "否"))
if lock_exists:
    try:
        with open(LOCK, "r", encoding="utf-8") as fh:
            raw = fh.read().strip()
        p("锁内容: %s" % raw)
        # 解析 PID 与时间
        pid = None
        ts_str = None
        try:
            j = json.loads(raw)
            pid = j.get("pid", j.get("PID"))
            ts_str = j.get("time", j.get("timestamp", j.get("lock_time")))
        except Exception:
            import re
            m = re.search(r"\b(\d{4,})\b", raw)
            if m:
                pid = int(m.group(1))
            m2 = re.search(r"(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2})", raw)
            if m2:
                ts_str = m2.group(1)
        if pid is None:
            p("锁解析: 无法解析 PID")
        else:
            pid = int(pid)
            # ctypes OpenProcess 判断存活
            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            SYNCHRONIZE = 0x00100000
            h = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION | SYNCHRONIZE, False, pid)
            if h:
                # 再取退出码确认
                code = ctypes.c_ulong(0)
                ok = ctypes.windll.kernel32.GetExitCodeProcess(h, ctypes.byref(code))
                ctypes.windll.kernel32.CloseHandle(h)
                alive = ok and (code.value == 259)  # STILL_ACTIVE
            else:
                alive = False
            p("PID %d 存活: %s" % (pid, "是" if alive else "否"))
            if alive:
                p("锁状态: 正在运行(PID %d)" % pid)
            else:
                # 判断是否超 10 分钟僵尸
                stale_min = None
                if ts_str:
                    try:
                        ts_str_n = ts_str.replace("T", " ")
                        from datetime import datetime
                        lt = datetime.strptime(ts_str_n[:19], "%Y-%m-%d %H:%M:%S")
                        now = datetime.now()
                        stale_min = (now - lt).total_seconds() / 60.0
                    except Exception:
                        pass
                p("锁状态: 僵尸锁(需清理)")
                if stale_min is not None:
                    p("  加锁距今: %.1f 分钟%s" % (stale_min, " (>10min)" if stale_min > 10 else ""))
    except Exception as ex:
        p("[锁读取异常] %s" % ex)

sys.stdout.write("\n".join(out))
