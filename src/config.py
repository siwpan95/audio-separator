# -*- coding: utf-8 -*-
"""
配置模块 — 常量、配色、模型定义、路径解析。

所有运行时常量集中于此，修改配色 / 新增模型 / 调整路径只需改这一个文件。
"""

import os
import sys

# ============================== 路径 ============================== #

# 项目根目录（本文件上两级：src/config.py -> src/ -> 项目根）
PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 项目本地 venv 的 python 解释器路径。
# venv 基于 /Python314 创建，已安装 demucs / torch（CPU 版）。
# 若 venv 不存在则回退到当前解释器（假定依赖已就绪）。
VENV_PY = os.path.join(PROJECT_DIR, "venv", "Scripts", "python.exe")
if not os.path.isfile(VENV_PY):
    VENV_PY = sys.executable

# GUI 解释器（当前进程，需含 tkinter）
GUI_PY = sys.executable

# ============================== 音频格式 ============================== #

AUDIO_EXTS = (".mp3", ".wav", ".flac", ".m4a", ".ogg", ".wma", ".aac", ".aiff")

# ============================== 模型 ============================== #

# 可选模型（Demucs 预训练）
# 格式: (模型名, 显示标签)
MODELS = [
    ("htdemucs",      "htdemucs (默认，速度与质量平衡)"),
    ("htdemucs_ft",   "htdemucs_ft ★推荐 质量最高"),
    ("htdemucs_6s",   "htdemucs_6s (六轨：+吉他/钢琴)"),
    ("hdemucs_mmi",   "hdemucs_mmi (v3 重训基线)"),
    ("mdx",           "mdx (人声分离专长)"),
    ("mdx_extra",     "mdx_extra (人声分离增强)"),
    ("mdx_extra_q",   "mdx_extra_q (量化省显存)"),
    ("__bs_roformer__", "⚡ BS-RoFormer-SW 高级 (人声SOTA，六轨)"),
]

# BS-RoFormer 模型标识符（非 Demucs 模型）
BS_RF_MODEL_ID = "__bs_roformer__"

# 分离模式
# two  — 人声 / 伴奏（二轨），使用 --two-stems vocals
# four — 鼓 / 贝斯 / 人声 / 其他（四轨），默认行为
SEPARATION_MODES = [
    ("two",  "人声 / 伴奏（二轨）"),
    ("four", "鼓 / 贝斯 / 人声 / 其他（四轨）"),
]

# ============================== 配色（浅色主题） ============================== #

C_BG = "#f4f5f7"
C_PANEL = "#ffffff"
C_BORDER = "#e2e5ea"
C_TEXT = "#1f2329"
C_TEXT_DIM = "#6b7280"
C_PRIMARY = "#2563eb"
C_PRIMARY_HV = "#1d4ed8"
C_DANGER = "#dc2626"
C_DANGER_HV = "#b91c1c"
C_SUCCESS = "#16a34a"
C_LOG_BG = "#1e1f22"
C_LOG_FG = "#e6e6e6"
C_STATUS_BG = "#e9ebef"
C_HOVER = "#eef2ff"

# ============================== 字体 ============================== #

FONT_UI = ("Microsoft YaHei UI", 9)
FONT_TITLE = ("Microsoft YaHei UI", 16, "bold")
FONT_SUBTITLE = ("Microsoft YaHei UI", 9)
FONT_SECTION = ("Microsoft YaHei UI", 9, "bold")
FONT_BTN_PRIMARY = ("Microsoft YaHei UI", 10, "bold")
FONT_BTN = ("Microsoft YaHei UI", 10)
FONT_BTN_SMALL = ("Microsoft YaHei UI", 9)
FONT_LOG = ("Consolas", 9)
FONT_STATUS = ("Microsoft YaHei UI", 8)

# ============================== 默认参数 ============================== #

DEFAULT_MODEL = "htdemucs"
DEFAULT_MODE = "two"
DEFAULT_SHIFTS = 2

# demucs 环境检查超时（秒）
ENV_CHECK_TIMEOUT = 40

# ============================== 输出格式 ============================== #

# 输出音频格式（Demucs 默认输出 WAV，本工具支持后处理转码）
# wav — 无压缩，最快
# flac — 无损压缩，文件小
OUTPUT_FORMATS = [
    ("wav",  "WAV（无压缩，默认）"),
    ("flac", "FLAC（无损压缩）"),
]

DEFAULT_OUTPUT_FORMAT = "wav"

# ============================== 批量处理 ============================== #

# 批量模式：每次处理的最大文件数提示
BATCH_MAX_DISPLAY = 200

# ============================== 预设方案 ============================== #

# 一键配置：模型、模式、shifts、格式
PRESETS = [
    ("卡拉OK模式", {
        "desc": "人声/伴奏分离，快速",
        "model": "htdemucs", "mode": "two",
        "shifts": 2, "format": "wav",
    }),
    ("混音制作", {
        "desc": "四轨分离，平衡质量",
        "model": "htdemucs_ft", "mode": "four",
        "shifts": 2, "format": "wav",
    }),
    ("极致质量", {
        "desc": "最高质量，较慢",
        "model": "htdemucs_ft", "mode": "two",
        "shifts": 4, "format": "flac",
    }),
]

# ============================== 进度预估 ============================== #

# 各模型在 CPU 上的近似处理速度（相对于实时）
# 值越小越快：1.0 表示实时速度，0.04 表示 25x 实时（25秒处理1秒音频）
PROCESSING_SPEED = {
    "htdemucs":      0.04,   # ~25x 实时
    "htdemucs_ft":   0.01,   # ~100x 实时
    "htdemucs_6s":   0.015,  # ~65x 实时
    "hdemucs_mmi":   0.05,   # ~20x 实时
    "mdx":           0.06,   # ~17x 实时
    "mdx_extra":     0.05,   # ~20x 实时
    "mdx_extra_q":   0.08,   # ~12.5x 实时
    "bs_roformer":   0.005,  # ~200x 实时（极慢但质量最高）
}

# 消息队列轮询间隔（毫秒）
POLL_INTERVAL_MS = 80
