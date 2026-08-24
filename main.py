# -*- coding: utf-8 -*-
"""
音频分离工具 — 入口

启动方式：
    F:\\Python314\\python.exe main.py
或：
    run.bat
"""

import os
import sys

# 确保项目根目录在 sys.path 中（Python 3.11+ 不自动添加 cwd）
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import tkinter as tk
from src.ui.main_window import AudioSeparatorApp


def main():
    root = tk.Tk()
    AudioSeparatorApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
