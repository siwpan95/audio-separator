# -*- coding: utf-8 -*-
import os, json, sys

# 2026-09-23 去本地化：源/输出根按 环境变量 → 同级仓/同级盘 推导
# （原路径均已失效）
from pathlib import Path as _Path
_REPOS_ROOT = _Path(__file__).resolve().parent.parent          # …/repos
_ASSETS_ROOT = _REPOS_ROOT.parent / "assets"                  # …/assets
RADIO_MUSIC = _Path(os.environ.get("RADIO_MUSIC_ROOT") or (_REPOS_ROOT / "private-radio-stations" / "apps" / "audio" / "music"))
RADIO_STEMS = _Path(os.environ.get("STEMS_ROOT") or (_ASSETS_ROOT / "radio_music_stems"))
CSMUSIC = _Path(os.environ.get("CSMUSIC_ROOT") or (_REPOS_ROOT.parent / "csmusic"))
CSMUSIC_STEMS = _Path(os.environ.get("CSMUSIC_STEMS_ROOT") or (_REPOS_ROOT.parent / "csmusic_stems"))

AUDIO_EXT = ('.mp3', '.flac', '.wav', '.m4a', '.ogg')

def count_done_stems(outdir):
    """统计输出目录下含至少 3 个 .wav 的子目录数量"""
    n = 0
    if not os.path.isdir(outdir):
        return 0
    for name in os.listdir(outdir):
        d = os.path.join(outdir, name)
        if not os.path.isdir(d):
            continue
        wavs = [f for f in os.listdir(d) if f.lower().endswith('.wav')]
        if len(wavs) >= 3:
            n += 1
    return n

def count_music(src, recursive=False):
    n = 0
    if recursive:
        for root, dirs, files in os.walk(src):
            for f in files:
                if f.lower().endswith(AUDIO_EXT):
                    n += 1
    else:
        if os.path.isdir(src):
            for f in os.listdir(src):
                if f.lower().endswith(AUDIO_EXT):
                    n += 1
    return n

def count_failed(progress_path):
    if not os.path.isfile(progress_path):
        return -1, 0
    try:
        data = json.load(open(progress_path, encoding='utf-8'))
    except Exception as e:
        return -2, 0
    total = 0
    failed = 0
    statuses = {}
    if isinstance(data, dict):
        # 可能是 {name: entry} 或 {'items': [...]}
        items = data.get('items') or data.get('songs') or data.get('progress')
        if items is None:
            items = list(data.values())
    elif isinstance(data, list):
        items = data
    else:
        items = []
    for it in items:
        if not isinstance(it, dict):
            continue
        total += 1
        st = it.get('status') or it.get('state') or ''
        statuses[st] = statuses.get(st, 0) + 1
        if st == 'failed':
            failed += 1
    return failed, total, statuses

def report(name, src, out, recursive=False):
    done = count_done_stems(out)
    total = count_music(src, recursive)
    remaining = max(0, total - done)
    progress_path = os.path.join(out, 'batch_progress.json')
    res = count_failed(progress_path)
    failed = res[0]
    extra = ''
    if len(res) >= 3:
        extra = str(res[2])
    print(f"[{name}] done_stems={done} total={total} remaining={remaining} failed={failed} statuses={extra}")

report('radio', str(RADIO_MUSIC), str(RADIO_STEMS), recursive=False)
report('csmusic', str(CSMUSIC), str(CSMUSIC_STEMS), recursive=True)
print("STAT_SENTINEL_DONE")
