# -*- coding: utf-8 -*-
"""
后处理链 — 分离完成后对音轨进行降噪 + 动态处理。

使用 noisereduce（频谱门控降噪）和 pedalboard（音频效果链）。
在分离完成后自动对所有输出 WAV 文件应用处理链。
"""

import os
import glob

import soundfile as sf
import numpy as np

try:
    import noisereduce as nr
    HAS_NOISEREDUCE = True
except ImportError:
    HAS_NOISEREDUCE = False

try:
    from pedalboard import Pedalboard, NoiseGate, Compressor, Gain, Reverb
    HAS_PEDALBOARD = True
except ImportError:
    HAS_PEDALBOARD = False


# 默认后处理参数
DEFAULT_POST_SETTINGS = {
    "denoise": True,           # 频谱降噪
    "denoise_strength": 0.7,   # 降噪强度 0-1（越大越激进）
    "noise_gate": True,        # 噪声门（去尾音/混响残留）
    "gate_threshold": -35,     # 门限 dB
    "compress": True,          # 动态压缩
    "compress_threshold": -18, # 压缩阈值 dB
    "compress_ratio": 3,       # 压缩比
    "gain": 0,                 # 输出增益 dB
}


def apply_post_chain(audio_dir, settings=None, on_log=None):
    """对目录中所有 WAV 文件应用后处理链。

    Args:
        audio_dir: 音频文件所在目录（递归查找 WAV）
        settings:  后处理参数字典，None=使用默认值
        on_log:    callback(str)
    Returns:
        int — 处理的文件数
    """
    if settings is None:
        settings = DEFAULT_POST_SETTINGS

    wav_files = glob.glob(os.path.join(audio_dir, "**", "*.wav"), recursive=True)
    if not wav_files:
        if on_log:
            on_log("⚠ 未找到 WAV 文件，跳过后处理。")
        return 0

    ok = 0
    for wav_path in wav_files:
        try:
            data, sr = sf.read(wav_path)
            processed = _process_audio(data, sr, settings)
            sf.write(wav_path, processed, sr)
            ok += 1
        except Exception as e:
            if on_log:
                name = os.path.basename(wav_path)
                on_log(f"  ✗ 后处理失败：{name} — {e}")

    if on_log:
        desc = _settings_desc(settings)
        on_log(f"✓ 后处理完成：{ok}/{len(wav_files)} 个文件 ({desc})")
    return ok


def _process_audio(data, sr, settings):
    """单段音频的后处理链。"""
    # 确保 float32
    if data.dtype != np.float32:
        data = data.astype(np.float32)
    if data.ndim == 1:
        data = data.reshape(-1, 1)  # pedalboard 需要 (samples, channels)

    # 1. 频谱降噪 (noisereduce)
    if settings.get("denoise") and HAS_NOISEREDUCE:
        strength = settings.get("denoise_strength", 0.7)
        data = nr.reduce_noise(
            y=data.T,  # noisereduce 需要 (channels, samples)
            sr=sr,
            stationary=False,
            prop_decrease=strength,
        )
        data = data.T

    # 2. pedalboard 效果链
    if HAS_PEDALBOARD:
        board = Pedalboard([])

        # 噪声门
        if settings.get("noise_gate"):
            board.append(NoiseGate(
                threshold_db=settings.get("gate_threshold", -35),
                ratio=2.0,
                attack_ms=1.0,
                release_ms=150,
            ))

        # 压缩器
        if settings.get("compress"):
            board.append(Compressor(
                threshold_db=settings.get("compress_threshold", -18),
                ratio=settings.get("compress_ratio", 3),
                attack_ms=5,
                release_ms=100,
            ))

        # 输出增益
        gain_db = settings.get("gain", 0)
        if gain_db != 0:
            board.append(Gain(gain_db=gain_db))

        if len(board) > 0:
            data = board(data, sr)

    # 限制输出范围，防止削波
    data = np.clip(data, -1.0, 1.0)
    return data


def _settings_desc(settings):
    """生成后处理参数描述文本。"""
    parts = []
    if settings.get("denoise"):
        parts.append(f"降噪({settings.get('denoise_strength', 0.7):.0%})")
    if settings.get("noise_gate"):
        parts.append(f"门限({settings.get('gate_threshold', -35)}dB)")
    if settings.get("compress"):
        parts.append(f"压缩({settings.get('compress_ratio', 3)}:1)")
    if settings.get("gain", 0) != 0:
        parts.append(f"增益({settings.get('gain', 0):+.0f}dB)")
    return ", ".join(parts) if parts else "无后处理"


def check_available():
    """检查后处理依赖是否可用。

    Returns:
        dict {noisereduce: bool, pedalboard: bool}
    """
    return {
        "noisereduce": HAS_NOISEREDUCE,
        "pedalboard": HAS_PEDALBOARD,
        "any": HAS_NOISEREDUCE or HAS_PEDALBOARD,
    }
