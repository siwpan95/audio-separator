# audio_separator

## 仓库角色定位（投资组合分级 ①）

> 本仓在 siwpan 投资组合（D:/projects/repos，共 133 仓）中定级为 **① 核心推进**，领域 **音乐/音频**，定位 **本地音乐流水线**。
> **角色**：Demucs/BS-RoFormer 人声分离桌面应用，持续投入。
> **维护策略**：① 核心推进——持续投入、不允许冻结；随所属收敛点 / 流水线长期演进。
> 投资组合统一分级索引：`D:/projects/repos/PORTFOLIO_TIERING.md`。

> 仓库：<https://gitee.com/siwpan/audio-separator> ｜ 许可：MIT（见 [LICENSE](LICENSE)）
> 注：文中 <PATH> 为路径占位符，请替换为你本机实际的目录 / 可执行文件路径。

音频分离工具 —— 基于 Demucs（以及 BS-RoFormer）的人声/伴奏分离桌面应用，附批量处理与 Web 服务入口。

## 语言 / 类型
- Python（Tkinter 桌面 GUI + 命令行批量脚本 + 标准库 Web 服务）

## 目录要点
- `main.py` —— Tkinter GUI 入口（`AudioSeparatorApp`）
- `src/` —— 核心实现：`demucs_runner.py`、`bs_roformer_runner.py`、`post_processor.py`、`web_server.py`、`config.py`
- `batch_separate_all.py` / `run_until_done.py` —— 批量/断点续跑脚本
- `models/` —— 本地模型；`venv/` —— 项目自有虚拟环境（torch 等重包）
- `run.bat` / `RUN_BATCH.bat` —— Windows 启动脚本
- `RESEARCH.md` —— 调研笔记；`test_sample.wav` / `no_vocals.wav` / `vocals.wav` —— 测试音频

## 运行方式与依赖
- 运行：`run.bat` 或 `python main.py`；批量用 `RUN_BATCH.bat`。
- 依赖（在项目 `venv` 内安装）：`torch` / `torchaudio`（需从 PyTorch CPU 索引安装），
  `demucs>=4.0`、`numpy`、`soundfile`。详见 `requirements.txt`。

## 端口登记（统一端口纪律，2026-08-24）

Web 服务默认端口 **8080**（src/web_server.py --port）已登记于 `<PATH>`；改端口前先查表。

## 任务日志（日志即事实源，2026-08-24）

批量脚本自动落盘 `<输出目录>/pipeline.log`（run_start/song_skip/song_start/song_done/song_error/run_end）。审计：

```bash
python batch_separate_all.py --tasks --output <输出目录> [--tasks-limit 100] [--tasks-json]
```

冒烟：`python test_tasklog.py`（3/3，零重依赖）。

## 测试状态
- `py_compile` 语法检查通过（16 个 .py 文件）。
- 重工具（依赖 torch/demucs 模型推理），本次仅编译未运行。
