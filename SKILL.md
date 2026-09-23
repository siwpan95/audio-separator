---
name: audio-separator
description: Maintain audio_separator (本 SKILL.md 所在仓库根). Demucs-based stem separation with batch script and task log.
agent_created: true
---

# audio_separator（人声/伴奏分离）维护

## 概述
基于 Demucs（+BS-RoFormer）的分离工具：Tkinter GUI + 批量脚本 batch_separate_all.py + Web 服务（src/web_server.py，默认端口 8080，登记于端口分配表）。

## 结构
- main.py：GUI；src/：demucs_runner/bs_roformer_runner/post_processor/web_server/config
- batch_separate_all.py：批量+断点续跑（--resume/--limit/--workers/--min-duration/--recursive/--dry-run）
- tasklog.py：任务日志（<输出目录>/pipeline.log）；models/：本地模型；venv/：项目自有 torch 环境

## 常用命令
- 批量：venv/Scripts/python.exe batch_separate_all.py --source ... --output ... --resume --limit 10
- 审计：python batch_separate_all.py --tasks --output <目录>
- 冒烟：python test_tasklog.py（3/3，零重依赖）

## 已知陷阱
- 分离走子进程 VENV_PY（批量脚本本身纯标准库，勿引入 torch 依赖）
- 模型需预置 torch hub 缓存（见脚本头部 MANUAL MODEL SETUP）
- 单实例锁 + 进度文件（batch_progress.json）已有，勿破坏 resume 语义
