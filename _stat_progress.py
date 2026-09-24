import os, json, glob

# 2026-09-23 去本地化：源/输出根按 环境变量 → 同级仓/同级盘 推导
# （原路径均已失效）
from pathlib import Path as _Path
_REPOS_ROOT = _Path(__file__).resolve().parent.parent          # …/repos
_ASSETS_ROOT = _REPOS_ROOT.parent / "assets"                  # …/assets
RADIO_MUSIC = _Path(os.environ.get("RADIO_MUSIC_ROOT") or (_REPOS_ROOT / "private-radio-stations" / "apps" / "audio" / "music"))
RADIO_STEMS = _Path(os.environ.get("STEMS_ROOT") or (_ASSETS_ROOT / "radio_music_stems"))
CSMUSIC = _Path(os.environ.get("CSMUSIC_ROOT") or (_REPOS_ROOT.parent / "csmusic"))
CSMUSIC_STEMS = _Path(os.environ.get("CSMUSIC_STEMS_ROOT") or (_REPOS_ROOT.parent / "csmusic_stems"))

def count_stems(outdir):
    n_stems = 0
    n_total = 0
    if os.path.isdir(outdir):
        for d in os.listdir(outdir):
            p = os.path.join(outdir, d)
            if os.path.isdir(p):
                n_total += 1
                wavs = glob.glob(os.path.join(p, '*.wav'))
                if len(wavs) >= 3:
                    n_stems += 1
    return n_stems, n_total

def count_music(srcdir, recursive):
    exts = ('*.mp3', '*.flac', '*.wav', '*.m4a', '*.ogg')
    n = 0
    if recursive:
        for root, dirs, files in os.walk(srcdir):
            for f in files:
                if f.lower().endswith(('.mp3', '.flac', '.wav', '.m4a', '.ogg')):
                    n += 1
    else:
        for e in exts:
            n += len(glob.glob(os.path.join(srcdir, e)))
    return n

def count_failed(progpath):
    if not os.path.isfile(progpath):
        return -1
    with open(progpath, encoding='utf-8') as f:
        data = json.load(f)
    recs = data if isinstance(data, list) else data.get('progress', data)
    if isinstance(recs, dict):
        recs = recs.get('songs', recs.get('records', []))
    if not isinstance(recs, list):
        return -1
    failed = sum(1 for r in recs if isinstance(r, dict) and r.get('status') == 'failed')
    return failed

# radio
rs, rt = count_stems(str(RADIO_STEMS))
rm = count_music(str(RADIO_MUSIC), False)
rf = count_failed(str(RADIO_STEMS / 'batch_progress.json'))
print(f"RADIO|stems={rs}|total_dirs={rt}|music={rm}|remaining={rm-rs}|failed={rf}")

# csmusic
cs, ct = count_stems(str(CSMUSIC_STEMS))
cm = count_music(str(CSMUSIC), True)
cf = count_failed(str(CSMUSIC_STEMS / 'batch_progress.json'))
print(f"CSMUSIC|stems={cs}|total_dirs={ct}|music={cm}|remaining={cm-cs}|failed={cf}")

# markers
print("RADIO_DONE=" + ("YES" if os.path.isfile(str(RADIO_STEMS / 'ALL_DONE.txt')) else "NO"))
print("CSMUSIC_DONE=" + ("YES" if os.path.isfile(str(CSMUSIC_STEMS / 'ALL_DONE.txt')) else "NO"))
