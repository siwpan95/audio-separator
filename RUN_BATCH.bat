@echo off
:: 自动循环拆解 — 持续跑直到全部完成
:: 双击启动，可直接关闭窗口（下次启动自动继续）
title Radio Music Separator — 自动拆解中...
F:\Python314\python.exe G:\tools\audio\audio_separator\run_until_done.py --batch 20 --cool-down 10
pause
