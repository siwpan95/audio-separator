#!/usr/bin/env python3
r"""
自动化全量拆解 — 循环执行直到全部音乐源完成
============================================
- 支持多个音乐源（radio + csmusic），按顺序推进，拆完一个接着下一个
- 每批处理 N 首（默认 10），批次间休息 30 秒
- --resume 自动跳过已处理歌曲
- 每个源完成后各自写入 <output>/ALL_DONE.txt
- 全部源完成后退出
- 支持中断重跑（下次启动自动继续）

用法:
    G:/tools/audio_separator/venv/Scripts/python.exe run_until_done.py [--batch N] [--cool-down S] [--max-batches N]

Windows 计划任务（开机自启 + 每 2 小时）:
    schtasks /create /tn "RadioMusicSeparator" /tr "G:\tools\audio\audio_separator\venv\Scripts\python.exe G:\tools\audio\audio_separator\run_until_done.py --batch 20" /sc onstart /rl highest
    schtasks /create /tn "RadioMusicSeparator_Hourly" /tr "G:\tools\audio\audio_separator\venv\Scripts\python.exe G:\tools\audio\audio_separator\run_until_done.py --batch 20" /sc hourly /mo 2 /rl highest
"""

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

# 路径按自身位置解析（开发目录与安装目录通用，补丁即差异 2026-08-27）
VENV_PY = Path(__file__).parent / "venv" / "Scripts" / "python.exe"
BATCH_SCRIPT = Path(__file__).parent / "batch_separate_all.py"

# 音乐源配置列表（按此顺序推进）
SOURCES = [
    {
        "name": "radio",
        "source": r"G:/radio/music",
        "output": r"G:/radio_music_stems",
        "recursive": False,
        "min_duration": 3,
        "max_duration": 1200,
    },
    {
        "name": "csmusic",
        "source": r"G:/csmusic",
        "output": r"G:/csmusic_stems",
        "recursive": True,
        "min_duration": 60,
        "max_duration": 1200,
    },
]

EXTS = ("*.mp3", "*.flac", "*.wav", "*.m4a", "*.ogg")


def done_file(src: dict) -> Path:
    return Path(src["output"]) / "ALL_DONE.txt"


def progress_file(src: dict) -> Path:
    return Path(src["output"]) / "batch_progress.json"


def count_remaining(src: dict) -> int:
    """统计某源还有多少歌曲待处理（用脚本口径：总数 - 已完成）。"""
    pf = progress_file(src)
    if not pf.exists():
        # 尚未开始，返回总数
        return count_total(src)
    data = json.loads(pf.read_text(encoding="utf-8"))
    done = {r["song_name"] for r in data if r.get("status") in ("done", "cached")}
    return max(0, count_total(src) - len(done))


def count_total(src: dict) -> int:
    music_root = Path(src["source"])
    total = 0
    for ext in EXTS:
        if src["recursive"]:
            total += len(list(music_root.rglob(ext)))
        else:
            total += len(list(music_root.glob(ext)))
    return total


def build_cmd(src: dict, batch_size: int) -> list[str]:
    cmd = [
        str(VENV_PY), str(BATCH_SCRIPT),
        "--resume",
        "--limit", str(batch_size),
        "--source", src["source"],
        "--output", src["output"],
        "--min-duration", str(src["min_duration"]),
        "--max-duration", str(src["max_duration"]),
    ]
    if src["recursive"]:
        cmd.append("--recursive")
    return cmd


def run_one_batch(src: dict, batch_size: int) -> bool:
    """执行一批，返回该源是否已完成（True=已完成，False=还有剩余）。"""
    cmd = build_cmd(src, batch_size)
    print(f"\n{'='*60}")
    print(f"[{datetime.now().strftime('%H:%M:%S')}] [{src['name']}] 启动批次 {batch_size} 首")
    print(f"{'='*60}")

    subprocess.run(cmd, cwd=str(BATCH_SCRIPT.parent))

    if done_file(src).exists():
        print(f"[{src['name']}] ✅ 完成标记已存在")
        return True
    remaining = count_remaining(src)
    print(f"[{src['name']}] 剩余约 {remaining} 首")
    return False


def main():
    parser = argparse.ArgumentParser(description="自动化全量拆解（多源）")
    parser.add_argument("--batch", type=int, default=10, help="每批处理数量")
    parser.add_argument("--cool-down", type=int, default=30, help="批次间冷却秒数")
    parser.add_argument("--max-batches", type=int, default=0, help="最多执行几批（0=不限）")
    args = parser.parse_args()

    print(f"🔥 自动循环拆解启动")
    print(f"   批次大小: {args.batch} 首")
    print(f"   冷却间隔: {args.cool_down}s")
    for s in SOURCES:
        print(f"   · {s['name']}: {s['source']} → {s['output']}" + ("（递归）" if s["recursive"] else ""))
    print()

    batch_count = 0
    try:
        while True:
            # 找到第一个未完成的源
            active = next((s for s in SOURCES if not done_file(s).exists()), None)
            if active is None:
                print(f"\n🎉 全部音乐源拆解完成！")
                for s in SOURCES:
                    print(f"   DONE: {done_file(s)}")
                break

            batch_count += 1
            finished = run_one_batch(active, args.batch)
            print(f"✅ 批次 {batch_count} 完成 [{active['name']}]" + ("（该源已完成）" if finished else ""))

            if args.max_batches and batch_count >= args.max_batches:
                print(f"\n⏸️ 达到最大批次数 {args.max_batches}，退出")
                break

            print(f"⏳ 冷却 {args.cool_down}s ...")
            time.sleep(args.cool_down)

    except KeyboardInterrupt:
        print(f"\n⏸️ 用户中断。已完成 {batch_count} 批。")
        print(f"  重新运行自动继续: {VENV_PY} {Path(__file__)}")

    print(f"\n总批次: {batch_count}")


if __name__ == "__main__":
    main()
