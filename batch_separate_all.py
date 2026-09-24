#!/usr/bin/env python3
r"""
批量音源分离 —— 遍历音乐源目录，调用 demucs 拆解 stems
===================================================================

用法:
    venv\Scripts\python.exe batch_separate_all.py [选项]   （在仓库根运行）

默认源/输出（radio）:
    源: RADIO_MUSIC_ROOT（默认 同级仓 private-radio-stations/apps/audio/music）  →  输出: STEMS_ROOT（默认 <盘>\assets\radio_music_stems）

纳入 csmusic（CS:GO 音乐盒：嵌套子目录 + 只拆完整音乐 >60s）:
    venv\Scripts\python.exe batch_separate_all.py \
        --source <csmusic源> --output <csmusic stems输出> \
        --recursive --min-duration 60 --resume --limit 10

选项:
    --dry-run        不执行分离，仅列出待处理文件
    --limit N        最多处理 N 首
    --resume         跳过已有 stems 目录的歌曲；并重新尝试上次失败的歌曲
    --source DIR     音乐源目录（默认 RADIO_MUSIC_ROOT）
    --output DIR     stems 输出目录（默认 STEMS_ROOT）
    --recursive      递归扫描子目录（源目录为嵌套结构时使用）
    --min-duration S 跳过短于 S 秒的音频（默认 3）
    --max-duration S 跳过长于 S 秒的音频（默认 1200，即 20 分钟）
    --workers N      并行处理 N 首（默认 1，CPU 分离建议 =1）

输出:
    <输出目录>/<歌手> - <歌名>/  （平铺源）
        ├── vocals.wav
        ├── drums.wav
        ├── bass.wav
        └── other.wav
    <输出目录>/<父目录>_<曲名>/  （--recursive 嵌套源，避免同名冲突）
        └── 同上四轨

    <输出目录>/instrument_pool.yaml   (汇总，供 album_maker 使用)

前置条件（必须）:
    1. 手动下载 htdemucs 模型到正确位置，见下方 MODEL_SETUP 注释。
    2. demucs 模型已缓存在 audio_separator/venv 中。

健壮性修复说明（2026-08-12）:
    * --resume 现在会丢弃 progress 中的 failed / skipped_too_long 记录，
      使失败歌曲在下次运行时【重新入队】，不再永久卡死。
    * 超时阈值改为【按音频时长动态计算】（至少 600s，约为时长的 4 倍 + 余量），
      避免超长 DJ mix（如 70 分钟）被误判为超时失败。
    * 时长超过 MAX_DURATION_SECONDS（默认 20 分钟）的歌曲标记为
      skipped_too_long 并跳过，而非占用整轮超时。
    * 同名多格式（如 .flac + .mp3 同 stem）按 stem 去重，只处理一次。
    * 失败记录会写入 error 字段，便于排查真实原因。
"""

# ═══════════════════════════════════════════════════════════════════════
# MANUAL MODEL SETUP ─── 在另一台有网络的机器上执行 ───────────────────
# ═══════════════════════════════════════════════════════════════════════
#
# 步骤 1（联网机器）: 下载模型文件
#   pip install huggingface_hub
#   from huggingface_hub import hf_hub_download
#   hf_hub_download('adefossez/HTDemucs', 'htdemucs.th', cache_dir='./demucs_cache')
#   hf_hub_download('adefossez/HTDemucs', 'htdemucs.yaml', cache_dir='./demucs_cache')
#   生成文件: ./demucs_cache/models--adefossez--HTDemucs/.../htdemucs.{th,yaml}
#
# 步骤 2（本机）: 复制到 torch hub 缓存目录
#   目标: %USERPROFILE%/.cache/torch/hub/checkpoints/htdemucs.th
#         %USERPROFILE%/.cache/torch/hub/checkpoints/htdemucs.yaml
#
# 步骤 3（本机）: 验证
#   venv\Scripts\python.exe -c "   （在仓库根执行）
#     import torch; from demucs import pretrained
#     m = pretrained.get_model('htdemucs'); print('OK:', m)
#   "
#   应输出 "OK: <HTDemucs ...>" 而非网络错误。
#
# ═══════════════════════════════════════════════════════════════════════

import argparse
import glob
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from datetime import datetime

# ── 默认配置（radio；可被命令行参数覆盖）────────────────────────────
# 2026-09-23 去本地化：原路径均已失效。
# 现按「环境变量优先 → 同级仓/同级盘推导」解析：
_REPOS_ROOT = Path(__file__).resolve().parent.parent          # …/repos
_ASSETS_ROOT = _REPOS_ROOT.parent / "assets"                  # …/assets
MUSIC_ROOT = Path(os.environ.get("RADIO_MUSIC_ROOT")
                  or (_REPOS_ROOT / "private-radio-stations" / "apps" / "audio" / "music"))
STEMS_ROOT = Path(os.environ.get("STEMS_ROOT")
                  or (_ASSETS_ROOT / "radio_music_stems"))
_VENV_LOCAL = Path(__file__).resolve().parent / "venv" / "Scripts" / "python.exe"
VENV_PY = Path(os.environ.get("AUDIO_SEPARATOR_VENV_PY")
               or (_VENV_LOCAL if _VENV_LOCAL.is_file() else Path(sys.executable)))
DEMUCS_MODEL = "htdemucs"       # 4 stems: vocals, drums, bass, other
# DEMUCS_MODEL = "htdemucs_6s"  # 6 stems: + guitar, piano（可选，处理更慢）

RECURSIVE = False                # 是否递归扫描子目录（嵌套源，如 csmusic）

MAX_RETRIES = 2
BASE_TIMEOUT = 600              # 最短超时（秒）
TIMEOUT_PER_SEC = 4.0           # 每 1 秒音频给 4 秒处理预算
TIMEOUT_MARGIN = 120            # 额外余量（模型加载等）
MAX_DURATION_SECONDS = 1200     # 20 分钟：超过则跳过（标记为 skipped_too_long）
MIN_DURATION_SECONDS = 3        # 短于 3 秒的可能是损坏文件，跳过
INSTRUMENT_POOL_YAML = STEMS_ROOT / "instrument_pool.yaml"
PROGRESS_FILE = STEMS_ROOT / "batch_progress.json"
LOCK_FILE = STEMS_ROOT / ".separating.lock"
LOCK_STALE_SECONDS = 7200   # 锁超过 2 小时视为失效，防止崩溃后死锁

# 已完成（用于 resume 跳过）的状态；failed / skipped_* 会被重新尝试
COMPLETED_STATUSES = ("done", "cached")

# ── Stem → InstrumentRole 映射 ─────────────────────────────────────
STEM_ROLE_MAP = {
    "vocals":  "melody",
    "drums":   "drum",
    "bass":    "bass",
    "other":   "chord",
    "guitar":  "chord",
    "piano":   "melody",
}


def get_duration(song: Path):
    """返回音频时长（秒），读取失败返回 None"""
    try:
        import soundfile as sf
        info = sf.info(str(song))
        return info.frames / float(info.samplerate)
    except Exception:
        return None


def compute_timeout(duration):
    """按时长动态计算超时阈值"""
    if not duration:
        return BASE_TIMEOUT + TIMEOUT_MARGIN
    return max(BASE_TIMEOUT, int(duration * TIMEOUT_PER_SEC) + TIMEOUT_MARGIN)


def collect_songs(root: Path, recursive: bool = False) -> list[Path]:
    r"""扫描音乐源目录，收集所有 mp3/flac/wav/m4a/ogg 文件。

    recursive=True 时递归扫描（嵌套结构，如 csmusic 的 <音乐盒>/<曲名>.mp3）。
    """
    songs = []
    for ext in ("*.mp3", "*.flac", "*.wav", "*.m4a", "*.ogg"):
        if recursive:
            songs.extend(root.rglob(ext))
        else:
            songs.extend(root.glob(ext))
    return sorted(songs)


def song_key(song: Path) -> str:
    """生成歌曲唯一标识（progress 里的 song_name）。

    平铺源：<歌手> - <歌名>（= song.stem）
    递归源：<父目录>_<曲名>，避免不同子目录同名曲目（如各音乐盒的"主菜单.mp3"）冲突。
    """
    if RECURSIVE:
        rel = song.relative_to(MUSIC_ROOT)
        return str(rel.with_suffix("")).replace("\\", "_").replace("/", "_")
    return song.stem


def song_output_dir(song: Path) -> Path:
    """映射: 歌曲 → 输出 stems 目录（安全文件名）"""
    name = song_key(song)
    safe = "".join(c if c.isalnum() or c in " _-()[]" else "_" for c in name)
    return STEMS_ROOT / safe


def song_has_stems(out_dir: Path) -> bool:
    """检查是否已有 stems（用于 resume）"""
    stems = list(out_dir.glob("*.wav"))
    return len(stems) >= 3  # 至少有 vocals, drums, bass 三轨


def separate_one(song: Path, out_dir: Path, timeout: int) -> tuple[bool, str]:
    """调用 demucs subprocess 拆一首歌，返回 (成功, 错误原因)"""
    cmd = [
        str(VENV_PY), "-m", "demucs",
        "-n", DEMUCS_MODEL,
        "-o", str(out_dir),              # demucs 在 <out_dir>/htdemucs/ 下产出平坦 {stem}.wav
        "--filename", "{stem}.{ext}",
        str(song),
    ]
    last_err = ""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            env = os.environ.copy()
            env["HF_HUB_OFFLINE"] = "1"
            # 强制 UTF-8：demucs 子进程内部 print 输出路径时，若路径含非 GBK 字符
            # （如 "Côme" 的 ô/ê），Windows 默认 GBK stdout 会抛 UnicodeEncodeError 导致失败。
            env["PYTHONIOENCODING"] = "utf-8"
            env["PYTHONUTF8"] = "1"
            result = subprocess.run(
                cmd, capture_output=True,
                timeout=timeout, env=env,
                encoding="utf-8", errors="replace",
            )
            if result.returncode == 0:
                return True, ""
            if "CUDA out of memory" in (result.stderr + result.stdout):
                last_err = "CUDA OOM"
                print(f"    ⚠️ OOM, retry {attempt}/{MAX_RETRIES}")
                time.sleep(5)
                continue
            tail = (result.stderr or result.stdout or "")[-400:].replace("\n", " ")
            last_err = f"demucs rc={result.returncode}: {tail}"
            return False, last_err
        except subprocess.TimeoutExpired:
            last_err = f"timeout>{timeout}s"
            print(f"    ⏰ timeout {attempt}/{MAX_RETRIES} (>{timeout}s)")
        except Exception as e:
            last_err = f"exc: {repr(e)[:300]}"
            return False, last_err
    return False, last_err


def move_stems(out_dir: Path) -> list[Path]:
    """demucs 产出 out_dir/htdemucs/ 下平坦 {stem}.wav，移到 out_dir/"""
    nested = out_dir / DEMUCS_MODEL  # out_dir/htdemucs/
    stems = []
    if nested.exists() and nested.is_dir():
        for wav in nested.glob("*.wav"):
            dst = out_dir / wav.name
            if dst.exists():
                dst.unlink()  # 覆盖前一首的残留
            wav.rename(dst)
            stems.append(dst)
        # 清理空目录
        shutil.rmtree(nested, ignore_errors=True)
    else:
        stems = list(out_dir.glob("*.wav"))
    return stems


def generate_instrument_pool_yaml(all_results: list[dict]):
    """生成汇总 YAML，供 album_maker 直接使用"""
    instruments = []
    for r in all_results:
        song = r["song_name"]
        stem_dir = r["stem_dir"]
        for stem_file in Path(stem_dir).glob("*.wav"):
            stem_name = stem_file.stem
            role = STEM_ROLE_MAP.get(stem_name, "chord")
            instruments.append({
                "name": f"{song}_{stem_name}",
                "role": role,
                "engine": "sampler",
                "sample_path": str(stem_file.resolve()),
                "volume": 0.7,
                "pan": 0.0,
            })

    yaml_lines = [
        f"# 自动生成 — {datetime.now().isoformat()}",
        f"# 来源: {MUSIC_ROOT}，模型: {DEMUCS_MODEL}",
        f"name: RadioMusic Instrument Pool",
        f"bpm: 120",
        f"key: C",
        f"scale: major",
        f"global_volume: 0.9",
        f"generation:",
        f"  diversity: 0.5",
        f"  humanize: true",
        f"  seed: 42",
        f"  chord_progression: dreamy",
        f"instruments:",
    ]
    for inst in instruments:
        yaml_lines.append(f"  - name: {inst['name']}")
        yaml_lines.append(f"    role: {inst['role']}")
        yaml_lines.append(f"    engine: sampler")
        yaml_lines.append(f"    sample_path: {inst['sample_path']}")
        yaml_lines.append(f"    volume: {inst['volume']}")
        yaml_lines.append(f"    pan: {inst['pan']}")

    INSTRUMENT_POOL_YAML.write_text("\n".join(yaml_lines), encoding="utf-8")
    print(f"\n📋 乐器池 YAML: {INSTRUMENT_POOL_YAML}  ({len(instruments)} 采样)")
    print(f"   使用方式: album_maker 引用 instrument_pool 段")


def save_progress(results: list[dict]):
    PROGRESS_FILE.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")


def load_progress() -> list[dict]:
    if PROGRESS_FILE.exists():
        return json.loads(PROGRESS_FILE.read_text(encoding="utf-8"))
    return []


def _pid_alive(pid: int) -> bool:
    """跨平台检查进程是否存活。Windows 用 ctypes OpenProcess，其他用 os.kill(pid,0)。"""
    if pid <= 0:
        return False
    if sys.platform.startswith("win"):
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            # PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            h = kernel32.OpenProcess(0x1000, False, pid)
            if h:
                kernel32.CloseHandle(h)
                return True
            return False
        except Exception:
            return False
    else:
        try:
            os.kill(pid, 0)
            return True
        except ProcessLookupError:
            return False
        except Exception:
            return False


def acquire_lock() -> bool:
    """获取单实例锁；已被存活的近期实例持有则返回 False。

    改进：除时间戳 TTL 外还会检查锁持有者进程是否真活着。
    若进程已死（崩溃/被结束），锁可立即被接管，无需干等 2 小时。
    """
    try:
        if LOCK_FILE.exists():
            age = time.time() - LOCK_FILE.stat().st_mtime
            holder = -1
            try:
                holder = int(LOCK_FILE.read_text(encoding="utf-8").split()[0])
            except Exception:
                holder = -1
            if age < LOCK_STALE_SECONDS and _pid_alive(holder):
                return False  # 真·运行中，让出
            # 锁已陈旧，或持有者进程已死 → 抢占
            try:
                LOCK_FILE.unlink()
            except Exception:
                pass
        LOCK_FILE.write_text(f"{os.getpid()} {datetime.now().isoformat()}", encoding="utf-8")
        return True
    except Exception:
        return True  # 悲观放行，避免死锁


def release_lock():
    try:
        if LOCK_FILE.exists():
            LOCK_FILE.unlink()
    except Exception:
        pass


def main():
    global MUSIC_ROOT, STEMS_ROOT, PROGRESS_FILE, LOCK_FILE, INSTRUMENT_POOL_YAML
    global MIN_DURATION_SECONDS, MAX_DURATION_SECONDS, RECURSIVE

    parser = argparse.ArgumentParser(description="批量音源分离")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--source", type=str, default=str(MUSIC_ROOT), help="音乐源目录（默认 RADIO_MUSIC_ROOT 或同级仓 private-radio-stations/apps/audio/music）")
    parser.add_argument("--output", type=str, default=str(STEMS_ROOT), help="stems 输出目录（默认 STEMS_ROOT 或 <盘>\\assets\\radio_music_stems）")
    parser.add_argument("--recursive", action="store_true", help="递归扫描子目录")
    parser.add_argument("--min-duration", type=int, default=3, help="跳过短于 S 秒的音频")
    parser.add_argument("--max-duration", type=int, default=1200, help="跳过长于 S 秒的音频")
    parser.add_argument("--tasks", action="store_true", help="审计任务事件日志（<输出目录>/pipeline.log）")
    parser.add_argument("--tasks-limit", type=int, default=100, help="--tasks 显示条数")
    parser.add_argument("--tasks-json", action="store_true", help="--tasks JSON 输出")
    args = parser.parse_args()

    # --tasks 审计（零重依赖，先于环境校验）
    if args.tasks:
        from tasklog import PipelineLog
        _log_path = Path(args.output) / "pipeline.log"
        if not _log_path.is_file():
            print(f"[tasks] 无任务日志: {_log_path}")
            sys.exit(1)
        _entries = PipelineLog(_log_path).read(limit=args.tasks_limit)
        if args.tasks_json:
            print(json.dumps(_entries, ensure_ascii=False, indent=2))
            sys.exit(0)
        print(f"任务日志 {_log_path}（最近 {len(_entries)} 条）：")
        for _e in _entries:
            _extra = " ".join(f"{k}={v}" for k, v in _e.items()
                              if k not in ("seq", "ts", "type", "stage", "run_id"))
            print(f"  #{_e['seq']} {_e['ts']} [{_e['type']}] {_extra}")
        _runs = sorted({_e.get("run_id") for _e in _entries if _e.get("run_id")})
        _errs = [_e for _e in _entries if _e["type"] == "song_error"]
        print(f"  涉及运行 {len(_runs)} 次，歌曲失败 {len(_errs)} 条")
        sys.exit(0)

    # 应用命令行参数覆盖默认配置
    MUSIC_ROOT = Path(args.source)
    STEMS_ROOT = Path(args.output)
    PROGRESS_FILE = STEMS_ROOT / "batch_progress.json"
    LOCK_FILE = STEMS_ROOT / ".separating.lock"
    INSTRUMENT_POOL_YAML = STEMS_ROOT / "instrument_pool.yaml"
    MIN_DURATION_SECONDS = args.min_duration
    MAX_DURATION_SECONDS = args.max_duration
    RECURSIVE = args.recursive

    # 0. 验证环境
    if not VENV_PY.exists():
        print(f"❌ audio_separator venv 不存在: {VENV_PY}")
        sys.exit(1)
    if not MUSIC_ROOT.exists():
        print(f"❌ 音乐源目录不存在: {MUSIC_ROOT}")
        sys.exit(1)

    # ── 任务事件日志（日志即事实源，<输出目录>/pipeline.log） ──
    from tasklog import PipelineLog
    tasklog = PipelineLog(STEMS_ROOT / "pipeline.log")
    run_id = PipelineLog.new_run_id()
    tasklog.append("run_start", run_id=run_id, source=str(MUSIC_ROOT),
                   output=str(STEMS_ROOT), resume=args.resume, limit=args.limit,
                   workers=args.workers, dry_run=args.dry_run)

    songs = collect_songs(MUSIC_ROOT, RECURSIVE)
    print(f"📂 源目录 {MUSIC_ROOT}: {len(songs)} 首歌曲" + ("（递归）" if RECURSIVE else ""))
    print(f"📂 输出目录: {STEMS_ROOT}")
    print(f"   时长过滤: {MIN_DURATION_SECONDS}s ~ {MAX_DURATION_SECONDS}s")
    print()

    # 1. 预处理：resume 时只保留已完成记录，失败的重新入队
    if args.resume:
        prev = load_progress()
        results = [r for r in prev if r.get("status") in COMPLETED_STATUSES]
        dropped = len(prev) - len(results)
        if dropped:
            print(f"♻️  resume: 丢弃 {dropped} 条失败/跳过记录，重新尝试")
    else:
        results = []

    processed_names = {r["song_name"] for r in results}

    # 2. 构建待处理列表：跳过已完成 / 已有 stems / 时长不合规，并统计跳过数
    pending = []
    skipped = 0
    for song in songs:
        key = song_key(song)
        if key in processed_names:
            continue
        out_dir = song_output_dir(song)
        if args.resume and song_has_stems(out_dir):
            print(f"⏭️  跳过（已有 stems）: {key}")
            results.append({"song_name": key, "stem_dir": str(out_dir), "status": "cached"})
            tasklog.append("song_skip", stage="cached", run_id=run_id, song=key)
            continue
        # 时长预过滤：在此阶段排除，避免短/超长文件占用 --limit 名额
        dur = get_duration(song)
        if dur is not None:
            if dur > MAX_DURATION_SECONDS:
                results.append({"song_name": key, "stem_dir": str(out_dir),
                                "status": "skipped_too_long", "error": f"duration {dur:.0f}s"})
                tasklog.append("song_skip", stage="too_long", run_id=run_id, song=key, duration_s=round(dur, 1))
                skipped += 1
                continue
            if dur < MIN_DURATION_SECONDS:
                results.append({"song_name": key, "stem_dir": str(out_dir),
                                "status": "skipped_too_short", "error": f"duration {dur:.1f}s"})
                tasklog.append("song_skip", stage="too_short", run_id=run_id, song=key, duration_s=round(dur, 1))
                skipped += 1
                continue
        pending.append(song)

    if args.limit:
        pending = pending[:args.limit]

    total = len(pending) + skipped
    print(f"待处理: {len(pending)} 首 {'(dry-run)' if args.dry_run else ''}（另有 {skipped} 首因时长被跳过）\n")

    # 3. Dry-run
    if args.dry_run:
        for i, song in enumerate(pending, 1):
            out = song_output_dir(song)
            dur = get_duration(song)
            dur_s = f" [{dur/60:.1f}min]" if dur else ""
            print(f"  {i:4d}. {song_key(song)[:70]} → {out.name}{dur_s}")
        print(f"\n共 {len(pending)} 首待处理。去掉 --dry-run 开始执行。")
        tasklog.append("run_end", run_id=run_id, ok=True, dry_run=True, pending=len(pending))
        return

    if not pending:
        print("✅ 无待处理歌曲。")
        save_progress(results)
        generate_instrument_pool_yaml([r for r in results if r["status"] in COMPLETED_STATUSES])
        done_file = STEMS_ROOT / "ALL_DONE.txt"
        done_file.write_text(f"全部完成！{datetime.now().isoformat()}\n", encoding="utf-8")
        print(f"🎉 写入完成标记: {done_file}")
        tasklog.append("run_end", run_id=run_id, ok=True, ok_songs=0, fail_songs=0,
                       skipped=skipped, total=total)
        return

    # 4. 批量处理
    STEMS_ROOT.mkdir(parents=True, exist_ok=True)

    # 单实例锁：避免 Windows 计划任务 与 WorkBuddy 自动化 同时运行产生竞争
    if not acquire_lock():
        print("⚠️ 另一实例正在运行（锁文件未过期），本次跳过。")
        return
    import atexit
    atexit.register(release_lock)

    ok = 0
    fail = 0

    for i, song in enumerate(pending, 1):
        stem = song_key(song)
        out_dir = song_output_dir(song)
        out_dir.mkdir(parents=True, exist_ok=True)

        timeout = compute_timeout(get_duration(song))
        print(f"[{i}/{len(pending)}] {stem[:60]} ...", end=" ", flush=True)
        t0 = time.time()
        tasklog.append("song_start", stage="separate", run_id=run_id, song=stem)

        success, err = separate_one(song, out_dir, timeout)
        if success:
            stems = move_stems(out_dir)
            elapsed = time.time() - t0
            print(f"✅ {len(stems)} stems ({elapsed:.0f}s)")
            results.append({"song_name": stem, "stem_dir": str(out_dir), "status": "done"})
            tasklog.append("song_done", stage="separate", run_id=run_id, song=stem,
                           stems=len(stems), duration_s=round(elapsed, 1))
            ok += 1
        else:
            print(f"❌ 失败: {err[:120]}")
            results.append({"song_name": stem, "stem_dir": str(out_dir), "status": "failed", "error": err})
            tasklog.append("song_error", stage="separate", run_id=run_id, song=stem,
                           error=str(err)[:200])
            fail += 1

        # 每 10 首保存进度 + 更新 YAML
        if i % 10 == 0:
            save_progress(results)
            generate_instrument_pool_yaml([r for r in results if r["status"] in COMPLETED_STATUSES])

    # 5. 最终汇总
    save_progress(results)
    generate_instrument_pool_yaml([r for r in results if r["status"] in COMPLETED_STATUSES])

    tasklog.append("run_end", run_id=run_id, ok=fail == 0, ok_songs=ok,
                   fail_songs=fail, skipped=skipped, total=total)

    print(f"\n{'='*60}")
    print(f"  完成: {ok} 成功 / {fail} 失败 / {skipped} 跳过 / {total} 总计")
    print(f"  乐器池: {INSTRUMENT_POOL_YAML}")
    print(f"  任务日志: {STEMS_ROOT / 'pipeline.log'}")
    print(f"{'='*60}")

    release_lock()


if __name__ == "__main__":
    main()
