import os, json, glob, time, ctypes

MUSIC_DIR = r"G:/radio/music"
STEMS_DIR = r"G:/radio_music_stems"
PROGRESS = os.path.join(STEMS_DIR, "batch_progress.json")
ALL_DONE = os.path.join(STEMS_DIR, "ALL_DONE.txt")
LOCK = os.path.join(STEMS_DIR, ".separating.lock")

EXTS = ["*.mp3", "*.flac", "*.wav", "*.m4a", "*.ogg"]

print("=== 1. 音乐总数 ===")
total_music = 0
per_ext = {}
for ext in EXTS:
    files = glob.glob(os.path.join(MUSIC_DIR, "**", ext), recursive=True)
    per_ext[ext] = len(files)
    total_music += len(files)
for ext in EXTS:
    print(f"  {ext}: {per_ext[ext]}")
print(f"  TOTAL: {total_music}")

print("\n=== 2. batch_progress.json status 分布 ===")
failed_names = []
status_dist = {}
if os.path.exists(PROGRESS):
    with open(PROGRESS, "r", encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, list):
        prog = data
    elif isinstance(data, dict):
        prog = data.get("progress", [])
    else:
        prog = []
    for info in prog:
        if isinstance(info, dict):
            st = info.get("status", "unknown")
            name = info.get("song_name", "?")
            status_dist[st] = status_dist.get(st, 0) + 1
            if st == "failed":
                failed_names.append(name)
    for st, c in sorted(status_dist.items(), key=lambda x: -x[1]):
        print(f"  {st}: {c}")
    print(f"  (progress 记录总数: {len(prog)})")
    if failed_names:
        print(f"  FAILED songs ({len(failed_names)}):")
        for n in failed_names:
            print(f"    - {n}")
    else:
        print("  FAILED: 无")
else:
    print("  batch_progress.json 不存在")

print("\n=== 3. stems 子目录统计 ===")
if os.path.isdir(STEMS_DIR):
    subdirs = [d for d in os.listdir(STEMS_DIR)
               if os.path.isdir(os.path.join(STEMS_DIR, d))]
    complete = []
    for d in subdirs:
        wavs = glob.glob(os.path.join(STEMS_DIR, d, "*.wav"))
        if len(wavs) >= 3:
            complete.append(d)
    print(f"  子目录总数: {len(subdirs)}")
    print(f"  含 >=3 个 .wav 的完整 stems 目录数: {len(complete)}")
else:
    print("  stems 目录不存在")

print("\n=== 4. ALL_DONE.txt ===")
if os.path.exists(ALL_DONE):
    print("  ALL_DONE.txt 存在 -> 全部完成")
else:
    print("  ALL_DONE.txt 不存在 -> 尚未全部完成")

print("\n=== 5. .separating.lock ===")
now = time.time()
if os.path.exists(LOCK):
    try:
        with open(LOCK, "r", encoding="utf-8") as f:
            content = f.read().strip()
        print(f"  锁文件内容: {content}")
        pid = None
        lock_time = None
        parts = content.split()
        if parts:
            try:
                pid = int(parts[0])
            except ValueError:
                pid = None
            if len(parts) > 1:
                lock_time = parts[1]
        alive = False
        if pid:
            PROCESS_QUERY_INFORMATION = 0x0400
            PROCESS_VM_READ = 0x0010
            try:
                h = ctypes.windll.kernel32.OpenProcess(
                    PROCESS_QUERY_INFORMATION | PROCESS_VM_READ, False, pid)
                if h:
                    alive = True
                    ctypes.windll.kernel32.CloseHandle(h)
            except Exception:
                alive = False
        print(f"  PID={pid} 存活={alive}")
        if lock_time:
            try:
                lt = time.mktime(time.strptime(lock_time, "%Y-%m-%dT%H:%M:%S.%f"))
                age_min = (now - lt) / 60.0
                print(f"  加锁时间: {lock_time} (约 {age_min:.1f} 分钟前)")
            except Exception:
                print(f"  加锁信息: {lock_time}")
        if alive:
            print("  结论: 正在运行(PID %s)" % pid)
        else:
            print("  结论: 僵尸锁(需清理) - PID 已死超过10分钟")
    except Exception as e:
        print(f"  读锁出错: {e}")
else:
    print("  .separating.lock 不存在 -> 当前无进程持锁")

print("\n=== 6. 总结 ===")
done_like = status_dist.get("done", 0) + status_dist.get("cached", 0)
failed = status_dist.get("failed", 0)
skipped = status_dist.get("skipped_too_long", 0) + status_dist.get("skipped_too_short", 0)
remaining = total_music - done_like - failed - skipped
pct = (done_like / total_music * 100) if total_music else 0
print(f"  已完成(含cached) {done_like} / 共 {total_music} 首 ({pct:.1f}%)")
print(f"  失败 {failed}, 跳过 {skipped}, 剩余 {max(remaining,0)}")
