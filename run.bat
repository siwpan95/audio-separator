@echo off
chcp 65001 >nul
title 音频分离工具 - Demucs
REM ============================================================
REM  GUI 进程：PATH 上的 python（含 tkinter）—— 原为旧机 F:\Python314\python.exe，已失效
REM  demucs 子进程：项目本地 venv（%~dp0venv）
REM  两者通过 subprocess 桥接，路径由 src/config.py 统一管理
REM ============================================================
set "PY=python"
where python >nul 2>nul || set "PY=%~dp0venv\Scripts\python.exe"
"%PY%" "%~dp0main.py"
if errorlevel 1 pause
