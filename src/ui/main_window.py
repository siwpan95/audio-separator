# -*- coding: utf-8 -*-
"""
主窗口 — AudioSeparatorApp

负责：
  - UI 构建（输入/输出/参数/按钮/进度条/日志/状态栏）
  - 用户交互回调（浏览、启动、停止、打开、清空）
  - 消息队列轮询（连接工作线程与主线程）
  - 状态管理（运行态/按钮启禁）

与 demucs_runner.DemucsRunner 完全解耦：
  UI 层通过回调接收进度 / 日志 / 完成 / 出错事件，
  无需关心子进程执行细节。
"""

import os
import queue
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from datetime import datetime

from ..config import (
    AUDIO_EXTS, MODELS, SEPARATION_MODES, OUTPUT_FORMATS, PRESETS,
    BS_RF_MODEL_ID,
    C_BG, C_PANEL, C_BORDER, C_TEXT, C_TEXT_DIM,
    C_PRIMARY, C_PRIMARY_HV, C_DANGER, C_DANGER_HV,
    C_SUCCESS, C_LOG_BG, C_LOG_FG, C_STATUS_BG, C_HOVER,
    FONT_UI, FONT_TITLE, FONT_SUBTITLE, FONT_SECTION,
    FONT_BTN_PRIMARY, FONT_BTN, FONT_BTN_SMALL,
    FONT_LOG, FONT_STATUS,
    VENV_PY, GUI_PY,
    DEFAULT_MODEL, DEFAULT_MODE, DEFAULT_SHIFTS,
    DEFAULT_OUTPUT_FORMAT, BATCH_MAX_DISPLAY,
    POLL_INTERVAL_MS,
)
from ..demucs_runner import DemucsRunner
from ..bs_roformer_runner import BsRoformerRunner
from ..post_processor import DEFAULT_POST_SETTINGS, check_available as check_post_available


class AudioSeparatorApp:
    """音频分离工具主窗口。"""

    def __init__(self, root):
        self.root = root
        self.root.title("音频分离工具 — Demucs")
        self.root.geometry("820x660")
        self.root.minsize(740, 600)
        self.root.configure(bg=C_BG)

        # 消息队列（线程 → 主线程）
        self.msg_queue = queue.Queue()

        # Demucs 运行器
        self.runner = DemucsRunner()

        # BS-RoFormer 运行器（高级模式）
        self.bsrf_runner = BsRoformerRunner()
        self.bsrf_ok = False  # BS-RoFormer 环境是否就绪

        # 状态
        self.env_ok = False   # demucs 环境是否就绪

        # 输入变量
        self.input_file = tk.StringVar()
        self.output_dir = tk.StringVar()
        self.mode = tk.StringVar(value=DEFAULT_MODE)
        self.model = tk.StringVar(value=DEFAULT_MODEL)
        self.shifts = tk.IntVar(value=DEFAULT_SHIFTS)
        self.output_format = tk.StringVar(value=DEFAULT_OUTPUT_FORMAT)

        # 批量模式
        self.batch_mode = tk.BooleanVar(value=False)
        self.file_list = []           # 批量文件路径列表

        # GPU 信息
        self.gpu_mode = "检测中…"     # GPU/CPU 状态文本
        self._current_audio_duration = 0  # 当前处理音频时长

        # 后处理
        self.post_enable = tk.BooleanVar(value=False)
        self.post_denoise_val = tk.DoubleVar(value=0.7)
        self.post_gate_val = tk.IntVar(value=-35)

        # 对比模式
        self.compare_mode = tk.BooleanVar(value=False)
        self._compare_model_map = {}  # 第二个模型标签→模型名映射
        self._compare_runner = DemucsRunner()  # 第二个运行器

        self._build_ui()
        self._poll_queue()
        self._check_env()
        self._check_gpu()
        self._check_bsrf_env()

    # ======================== UI 构建 ======================== #

    def _build_ui(self):
        self.root.option_add("*Font", FONT_UI)
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        # 外层容器
        outer = tk.Frame(self.root, bg=C_BG)
        outer.pack(fill="both", expand=True, padx=18, pady=14)

        # 标题
        tk.Label(
            outer, text="音频分离工具", bg=C_BG, fg=C_TEXT,
            font=FONT_TITLE,
        ).pack(anchor="w")
        tk.Label(
            outer, text="基于 Meta Demucs · 人声/伴奏分离 · 多轨分离",
            bg=C_BG, fg=C_TEXT_DIM, font=FONT_SUBTITLE,
        ).pack(anchor="w", pady=(2, 12))

        # ---- 输入卡片 ----
        self._section_card(outer, " 输入音频 ",
                           self._build_input_panel)

        # ---- 输出卡片 ----
        self._section_card(outer, " 输出目录 ",
                           self._build_output_panel)

        # ---- 参数卡片 ----
        self._section_card(outer, " 分离参数 ",
                           self._build_options_panel)

        # ---- 预设方案 ----
        self._build_preset_bar(outer)

        # ---- 操作按钮 ----
        self._build_button_bar(outer)

        # ---- 进度条 ----
        self._build_progress_bar(outer)

        # ---- 日志 ----
        self._build_log_panel(outer)

        # ---- 状态栏 ----
        self._build_status_bar()

        # 欢迎信息
        self.log("欢迎使用音频分离工具。")
        self.log(f"GUI 解释器：{GUI_PY}")
        self.log(f"Demucs 解释器：{VENV_PY}")
        self.log("首次运行时 Demucs 会自动下载模型（约 80MB），请耐心等待。")
        self.log("")

    # ---- 卡片容器 ----

    def _section_card(self, parent, label, content_fn):
        """统一卡片容器：标签栏 + 内边距 + 内容函数。"""
        card = tk.LabelFrame(
            parent, text=label, bg=C_PANEL, fg=C_TEXT,
            relief="flat", font=FONT_SECTION,
            highlightbackground=C_BORDER,
            highlightthickness=1, bd=0,
        )
        card.pack(fill="x", pady=(0, 10))
        inner = tk.Frame(card, bg=C_PANEL)
        inner.pack(fill="x", padx=12, pady=10)
        content_fn(inner)

    # ---- 输入面板 ----

    def _build_input_panel(self, inner):
        # 行0：模式切换
        mode_row = tk.Frame(inner, bg=C_PANEL)
        mode_row.grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 6))
        ttk.Checkbutton(
            mode_row, text="批量模式（同时处理多个文件）",
            variable=self.batch_mode, command=self._toggle_batch_mode,
        ).pack(side="left")

        # 行1：单文件输入（默认可见）
        self._single_row = tk.Frame(inner, bg=C_PANEL)
        self._single_row.grid(row=1, column=0, columnspan=3, sticky="we")
        tk.Label(self._single_row, text="文件：", bg=C_PANEL, fg=C_TEXT).pack(
            side="left", padx=(0, 6))
        self.entry_in = tk.Entry(
            self._single_row, textvariable=self.input_file,
            bg=C_PANEL, fg=C_TEXT, relief="solid", bd=1,
            highlightthickness=0, width=55,
        )
        self.entry_in.pack(side="left", fill="x", expand=True, padx=(0, 6))
        self.btn_browse_in = tk.Button(
            self._single_row, text="浏览…", command=self.browse_input,
            bg=C_PANEL, fg=C_TEXT, relief="solid", bd=1,
            activebackground=C_HOVER, cursor="hand2",
        )
        self.btn_browse_in.pack(side="left")

        # 行2+：批量文件列表（默认隐藏）
        self._batch_frame = tk.Frame(inner, bg=C_PANEL)
        self._batch_frame.grid(row=2, column=0, columnspan=3, sticky="we")
        self._batch_frame.grid_remove()

        btn_row = tk.Frame(self._batch_frame, bg=C_PANEL)
        btn_row.pack(fill="x")
        tk.Button(
            btn_row, text="+ 添加文件", command=self._batch_add_files,
            bg=C_PANEL, fg=C_TEXT, relief="solid", bd=1,
            activebackground=C_HOVER, cursor="hand2",
            font=FONT_BTN_SMALL,
        ).pack(side="left")
        tk.Button(
            btn_row, text="+ 添加文件夹", command=self._batch_add_folder,
            bg=C_PANEL, fg=C_TEXT, relief="solid", bd=1,
            activebackground=C_HOVER, cursor="hand2",
            font=FONT_BTN_SMALL,
        ).pack(side="left", padx=(6, 0))
        tk.Button(
            btn_row, text="清空列表", command=self._batch_clear,
            bg=C_PANEL, fg=C_TEXT_DIM, relief="solid", bd=1,
            activebackground="#f3f4f6", cursor="hand2",
            font=FONT_BTN_SMALL,
        ).pack(side="right")
        self._batch_count = tk.Label(
            btn_row, text="已选 0 个文件",
            bg=C_PANEL, fg=C_TEXT_DIM, font=FONT_UI,
        )
        self._batch_count.pack(side="right", padx=(0, 10))

        list_frame = tk.Frame(self._batch_frame, bg=C_PANEL)
        list_frame.pack(fill="x", pady=(4, 0))
        self._batch_listbox = tk.Listbox(
            list_frame, bg=C_PANEL, fg=C_TEXT,
            relief="solid", bd=1, highlightthickness=0,
            height=5, selectmode="extended",
            font=("Consolas", 9),
        )
        self._batch_listbox.pack(fill="x", expand=True)
        inner.columnconfigure(1, weight=1)

    # ---- 输出面板 ----

    def _build_output_panel(self, inner):
        tk.Label(inner, text="目录：", bg=C_PANEL, fg=C_TEXT).grid(
            row=0, column=0, sticky="w", padx=(0, 6))
        self.entry_out = tk.Entry(
            inner, textvariable=self.output_dir,
            bg=C_PANEL, fg=C_TEXT, relief="solid",
            bd=1, highlightthickness=0,
        )
        self.entry_out.grid(row=0, column=1, sticky="we", padx=(0, 6))
        self.btn_browse_out = tk.Button(
            inner, text="浏览…", command=self.browse_output,
            bg=C_PANEL, fg=C_TEXT, relief="solid", bd=1,
            activebackground=C_HOVER, cursor="hand2",
        )
        self.btn_browse_out.grid(row=0, column=2)
        inner.columnconfigure(1, weight=1)

    # ---- 参数面板 ----

    def _build_options_panel(self, inner):
        # 分离模式（行0）
        tk.Label(inner, text="分离模式：", bg=C_PANEL, fg=C_TEXT).grid(
            row=0, column=0, sticky="w", padx=(0, 6), pady=4)
        mode_box = tk.Frame(inner, bg=C_PANEL)
        mode_box.grid(row=0, column=1, sticky="w", pady=4)
        for i, (val, label) in enumerate(SEPARATION_MODES):
            tk.Radiobutton(
                mode_box, text=label, variable=self.mode, value=val,
                bg=C_PANEL, fg=C_TEXT, activebackground=C_PANEL,
                selectcolor=C_PANEL, cursor="hand2",
            ).pack(side="left", padx=(16 if i > 0 else 0, 0))

        # 模型（行1）— 显示描述标签，内部映射回模型名
        tk.Label(inner, text="模型：", bg=C_PANEL, fg=C_TEXT).grid(
            row=1, column=0, sticky="w", padx=(0, 6), pady=4)
        self._model_labels = [m[1] for m in MODELS]
        self._model_map = {m[1]: m[0] for m in MODELS}
        # 找到默认模型的显示标签
        default_label = next(m[1] for m in MODELS if m[0] == DEFAULT_MODEL)
        self.model_cb = ttk.Combobox(
            inner, state="readonly", width=30,
            values=self._model_labels,
        )
        self.model_cb.set(default_label)
        self.model_cb.grid(row=1, column=1, sticky="w", pady=4)

        # 对比模式 checkbox
        tk.Checkbutton(
            inner, text="对比模式（同时运行两个模型）",
            variable=self.compare_mode, bg=C_PANEL, fg=C_TEXT,
            activebackground=C_PANEL, selectcolor=C_PANEL,
            cursor="hand2", command=self._toggle_compare,
        ).grid(row=1, column=2, sticky="w", padx=(10, 0), pady=4)

        # 第二个模型选择（默认隐藏）
        self._compare_row = tk.Frame(inner, bg=C_PANEL)
        self._compare_row.grid(row=1, column=1, columnspan=2, sticky="we",
                               pady=(24, 0))
        self._compare_row.grid_remove()
        tk.Label(self._compare_row, text="模型 B：", bg=C_PANEL,
                 fg=C_PRIMARY, font=FONT_UI).pack(side="left", padx=(0, 6))
        compare_labels = [m[1] for m in MODELS if m[0] != BS_RF_MODEL_ID]
        self._compare_model_map = {m[1]: m[0] for m in MODELS}
        self._compare_cb = ttk.Combobox(
            self._compare_row, state="readonly", width=20,
            values=compare_labels,
        )
        if compare_labels:
            self._compare_cb.set(compare_labels[min(1, len(compare_labels)-1)])
        self._compare_cb.pack(side="left")

        # 位移次数（行2）
        tk.Label(inner, text="位移次数：", bg=C_PANEL, fg=C_TEXT).grid(
            row=2, column=0, sticky="w", padx=(0, 6), pady=4)
        spin = ttk.Spinbox(
            inner, from_=0, to=10, width=6,
            textvariable=self.shifts,
        )
        spin.grid(row=2, column=1, sticky="w", pady=4)
        tk.Label(
            inner,
            text="(越大质量越高但越慢，推荐 2-4)",
            bg=C_PANEL, fg=C_TEXT_DIM,
        ).grid(row=2, column=2, sticky="w", padx=(10, 0), pady=4)

        # 输出格式（行3）— 新增
        tk.Label(inner, text="输出格式：", bg=C_PANEL, fg=C_TEXT).grid(
            row=3, column=0, sticky="w", padx=(0, 6), pady=4)
        fmt_box = tk.Frame(inner, bg=C_PANEL)
        fmt_box.grid(row=3, column=1, sticky="w", pady=4)
        for i, (val, label) in enumerate(OUTPUT_FORMATS):
            tk.Radiobutton(
                fmt_box, text=label, variable=self.output_format, value=val,
                bg=C_PANEL, fg=C_TEXT, activebackground=C_PANEL,
                selectcolor=C_PANEL, cursor="hand2",
            ).pack(side="left", padx=(16 if i > 0 else 0, 0))

        # 后处理（行4）
        tk.Checkbutton(
            inner, text="后处理（降噪 + 噪声门 + 压缩）",
            variable=self.post_enable, bg=C_PANEL, fg=C_TEXT,
            activebackground=C_PANEL, selectcolor=C_PANEL,
            cursor="hand2",
        ).grid(row=4, column=0, columnspan=3, sticky="w", pady=(6, 2))

        post_row = tk.Frame(inner, bg=C_PANEL)
        post_row.grid(row=5, column=0, columnspan=3, sticky="w")
        tk.Label(post_row, text="降噪:", bg=C_PANEL, fg=C_TEXT_DIM,
                 font=FONT_STATUS).pack(side="left")
        ttk.Scale(post_row, from_=0, to=1, variable=self.post_denoise_val,
                  length=80).pack(side="left", padx=4)
        tk.Label(post_row, text="门限:", bg=C_PANEL, fg=C_TEXT_DIM,
                 font=FONT_STATUS).pack(side="left", padx=(8, 0))
        ttk.Scale(post_row, from_=-50, to=-10, variable=self.post_gate_val,
                  length=80).pack(side="left", padx=4)
        tk.Label(post_row, text="dB", bg=C_PANEL, fg=C_TEXT_DIM,
                 font=FONT_STATUS).pack(side="left")

    def _build_preset_bar(self, outer):
        preset_frame = tk.Frame(outer, bg=C_BG)
        preset_frame.pack(fill="x", pady=(0, 6))
        tk.Label(preset_frame, text="预设方案：", bg=C_BG, fg=C_TEXT_DIM,
                 font=FONT_UI).pack(side="left", padx=(0, 6))
        for name, cfg in PRESETS:
            btn = tk.Button(
                preset_frame, text=f"{name}", bg=C_PANEL,
                fg=C_TEXT, relief="solid", bd=1,
                activebackground=C_HOVER, cursor="hand2",
                font=FONT_BTN_SMALL,
                command=lambda c=cfg: self._apply_preset(c),
            )
            btn.pack(side="left", padx=3)
            self._make_tooltip(btn, cfg["desc"])

    def _make_tooltip(self, widget, text):
        """简易悬停提示（在状态栏显示）。"""
        def enter(e):
            self.status.config(text=text, fg=C_TEXT)
        def leave(e):
            self.status.config(
                text=(f"GPU: {self.gpu_mode}  ·  Demucs: {VENV_PY}"
                      if self.env_ok else f"GPU: {self.gpu_mode}")[:100],
                fg=C_SUCCESS if self.env_ok else C_TEXT_DIM)
        widget.bind("<Enter>", enter)
        widget.bind("<Leave>", leave)

    def _apply_preset(self, cfg):
        """应用预设配置。"""
        self.mode.set(cfg["mode"])
        self.shifts.set(cfg["shifts"])
        self.output_format.set(cfg["format"])
        model_name = cfg["model"]
        for label, mname in self._model_map.items():
            if mname == model_name:
                self.model_cb.set(label)
                break
        self.log(f">>> 已应用预设方案：{model_name}  |  "
                 f"模式={cfg['mode']}  |  shifts={cfg['shifts']}  |  "
                 f"格式={cfg['format']}")

    # ---- 操作按钮 ----

    def _build_button_bar(self, outer):
        btn_bar = tk.Frame(outer, bg=C_BG)
        btn_bar.pack(fill="x", pady=(4, 10))

        self.btn_start = tk.Button(
            btn_bar, text="▶  开始分离", command=self.start,
            bg=C_PRIMARY, fg="white", relief="flat", bd=0,
            activebackground=C_PRIMARY_HV, cursor="hand2",
            font=FONT_BTN_PRIMARY, height=1, width=14,
        )
        self.btn_start.pack(side="left")

        self.btn_stop = tk.Button(
            btn_bar, text="■  停止", command=self.stop,
            bg=C_DANGER, fg="white", relief="flat", bd=0,
            activebackground=C_DANGER_HV, cursor="hand2",
            state="disabled", font=FONT_BTN, height=1, width=10,
        )
        self.btn_stop.pack(side="left", padx=(8, 0))

        self.btn_open = tk.Button(
            btn_bar, text="📂 打开输出目录", command=self.open_output,
            bg=C_PANEL, fg=C_TEXT, relief="solid", bd=1,
            activebackground=C_HOVER, cursor="hand2",
            font=FONT_BTN_SMALL, height=1, width=16,
        )
        self.btn_open.pack(side="left", padx=(8, 0))

        self.btn_clear = tk.Button(
            btn_bar, text="清空日志", command=self.clear_log,
            bg=C_PANEL, fg=C_TEXT_DIM, relief="solid", bd=1,
            activebackground="#f3f4f6", cursor="hand2",
            font=FONT_BTN_SMALL, height=1, width=10,
        )
        self.btn_clear.pack(side="right")

    # ---- 进度条 ----

    def _build_progress_bar(self, outer):
        prog_frame = tk.Frame(outer, bg=C_BG)
        prog_frame.pack(fill="x", pady=(0, 6))
        self.prog_label = tk.Label(
            prog_frame, text="就绪", bg=C_BG, fg=C_TEXT_DIM,
            font=FONT_UI,
        )
        self.prog_label.pack(anchor="w")
        self.progress = ttk.Progressbar(
            prog_frame, mode="determinate", maximum=100,
        )
        self.progress.pack(fill="x", pady=(2, 0))
        self.eta_label = tk.Label(
            prog_frame, text="", bg=C_BG, fg=C_TEXT_DIM,
            font=FONT_STATUS,
        )
        self.eta_label.pack(anchor="e")

    # ---- 日志面板 ----

    def _build_log_panel(self, outer):
        log_card = tk.LabelFrame(
            outer, text=" 日志 ", bg=C_PANEL, fg=C_TEXT,
            font=FONT_SECTION,
            highlightbackground=C_BORDER,
            highlightthickness=1, bd=0,
        )
        log_card.pack(fill="both", expand=True, pady=(8, 0))

        log_inner = tk.Frame(log_card, bg=C_LOG_BG)
        log_inner.pack(fill="both", expand=True, padx=1, pady=1)

        self.log_text = tk.Text(
            log_inner, wrap="word", bg=C_LOG_BG, fg=C_LOG_FG,
            relief="flat", bd=0, highlightthickness=0,
            font=FONT_LOG, insertbackground=C_LOG_FG,
        )
        self.log_text.pack(side="left", fill="both", expand=True)

        scroll = ttk.Scrollbar(log_inner, command=self.log_text.yview)
        scroll.pack(side="right", fill="y")
        self.log_text.config(yscrollcommand=scroll.set)

    # ---- 状态栏 ----

    def _build_status_bar(self):
        self.status = tk.Label(
            self.root, text="GUI：" + GUI_PY,
            bg=C_STATUS_BG, fg=C_TEXT_DIM, anchor="w",
            font=FONT_STATUS,
        )
        self.status.pack(fill="x", side="bottom")

    # ======================== 交互回调 ======================== #

    def browse_input(self):
        path = filedialog.askopenfilename(
            title="选择音频文件",
            filetypes=[
                ("音频文件", " ".join(f"*{e}" for e in AUDIO_EXTS)),
                ("所有文件", "*.*"),
            ],
        )
        if path:
            self.input_file.set(path)
            if not self.output_dir.get():
                base = os.path.dirname(path)
                self.output_dir.set(os.path.join(base, "separated"))

    def browse_output(self):
        path = filedialog.askdirectory(title="选择输出目录")
        if path:
            self.output_dir.set(path)

    def start(self):
        if self.runner.is_running:
            return
        if not self.env_ok:
            messagebox.showerror(
                "环境未就绪",
                "demucs 环境检查未通过，无法启动分离。\n"
                "请检查日志中的错误信息，或确认依赖已安装：\n"
                "  pip install torch torchaudio\n"
                "  pip install demucs numpy soundfile",
            )
            return

        out_dir = self.output_dir.get().strip()
        if not out_dir:
            messagebox.showwarning("提示", "请选择输出目录。")
            return
        try:
            os.makedirs(out_dir, exist_ok=True)
        except OSError as e:
            messagebox.showerror("错误", f"无法创建输出目录：\n{e}")
            return

        model = self._get_model_name()
        mode = self.mode.get()
        shifts = self.shifts.get()
        fmt = self.output_format.get()

        # 批量模式
        if self.batch_mode.get():
            if not self.file_list:
                messagebox.showwarning("提示", "批量列表为空，请先添加文件。")
                return
            self._set_running_state(True)
            self.progress["value"] = 0
            self.prog_label.config(text="批量处理准备中…", fg=C_TEXT)
            self._current_batch_total = len(self.file_list)
            self.log(f">>> 开始批量处理 {len(self.file_list)} 个文件")
            self.log(f">>> 模型：{model}  模式：{mode}  shifts={shifts}  格式：{fmt}")
            self.runner.run_batch(
                self.file_list, out_dir, model, mode, shifts, fmt,
                on_file_start=lambda idx, total, name:
                    self.msg_queue.put(("batch_file_start", (idx, total, name))),
                on_file_done=lambda idx, total:
                    self.msg_queue.put(("batch_file_done", (idx, total))),
                on_file_error=lambda idx, reason:
                    self.msg_queue.put(("batch_file_error", (idx, reason))),
                on_batch_progress=lambda pct:
                    self.msg_queue.put(("progress", pct)),
                on_log=lambda msg: self.msg_queue.put(("log", msg)),
                on_all_done=lambda: self.msg_queue.put(("batch_all_done", None)),
            )
            return

        # 单文件模式 — BS-RoFormer 引擎
        if model == BS_RF_MODEL_ID:
            if not self.bsrf_ok:
                messagebox.showerror(
                    "BS-RoFormer 未就绪",
                    "BS-RoFormer 环境检查未通过。\n"
                    "请确认已安装：pip install bs-roformer-infer\n"
                    "首次使用需下载模型（约 700MB），请查看日志。")
                return
            in_path = self.input_file.get().strip()
            if not in_path or not os.path.isfile(in_path):
                messagebox.showwarning("提示", "请先选择有效音频文件。")
                return
            self._set_running_state(True)
            self.progress["value"] = 0
            self.prog_label.config(text="BS-RoFormer 准备中…", fg=C_TEXT)
            self._current_audio_duration = DemucsRunner.get_audio_duration(in_path)
            self.bsrf_runner.run(
                in_path, out_dir,
                on_log=lambda msg: self.msg_queue.put(("log", msg)),
                on_progress=lambda pct: self.msg_queue.put(("progress", pct)),
                on_done=lambda: self.msg_queue.put(("done", None)),
                on_error=lambda: self.msg_queue.put(("error", None)),
            )
            return

        # 对比模式 — 依次运行两个模型
        if self.compare_mode.get():
            if not self.env_ok:
                messagebox.showerror("环境未就绪", "demucs 未就绪。")
                return
            in_path = self.input_file.get().strip()
            if not in_path or not os.path.isfile(in_path):
                messagebox.showwarning("提示", "请先选择有效音频文件。")
                return
            model_b_label = self._compare_cb.get()
            model_b = self._compare_model_map.get(model_b_label, DEFAULT_MODEL)
            self._set_running_state(True)
            self.progress["value"] = 0
            self.prog_label.config(text="对比模式：模型 A 处理中…", fg=C_TEXT)
            self._current_audio_duration = DemucsRunner.get_audio_duration(in_path)
            if self._current_audio_duration > 0:
                self.log(f"音频时长：{self._current_audio_duration:.1f} 秒")
            self.log(f">>> 对比模式：{model} vs {model_b}")
            self._compare_phase = 1  # phase 1 = model A, 2 = model B
            post = self._get_post_settings()

            def run_phase1():
                cmd_a = self.runner.build_command(in_path, out_dir, model, mode, shifts)
                self.log(f">>> 模型 A ({model})：{' '.join(cmd_a[1:])}")
                self.runner.run(
                    cmd_a,
                    on_log=lambda msg: self.msg_queue.put(("log", msg)),
                    on_progress=lambda pct: self.msg_queue.put(("progress", pct)),
                    on_done=lambda: self.msg_queue.put(("compare_phase1_done", None)),
                    on_error=lambda: self.msg_queue.put(("compare_error", "A")),
                    output_format=fmt, output_dir=out_dir, post_process=post,
                )
            run_phase1()
            return

        # 单文件模式 — Demucs 引擎
        in_path = self.input_file.get().strip()
        if not in_path:
            messagebox.showwarning("提示", "请先选择输入音频文件。")
            return
        if not os.path.isfile(in_path):
            messagebox.showerror("错误", f"文件不存在：\n{in_path}")
            return

        # 获取音频时长用于进度预估
        self._current_audio_duration = DemucsRunner.get_audio_duration(in_path)
        if self._current_audio_duration > 0:
            self.log(f"音频时长：{self._current_audio_duration:.1f} 秒")

        self._set_running_state(True)
        self.progress["value"] = 0
        self.prog_label.config(text="正在启动…", fg=C_TEXT)

        cmd = self.runner.build_command(in_path, out_dir, model, mode, shifts)
        self.log(f">>> 启动 Demucs：{' '.join(cmd[1:])}")

        def on_done():
            self.msg_queue.put(("done", None))
            # 格式转换（在 done 消息已入队后，由 UI 线程在 _finish 中触发）

        self.runner.run(
            cmd,
            on_log=lambda msg: self.msg_queue.put(("log", msg)),
            on_progress=lambda pct: self.msg_queue.put(("progress", pct)),
            on_done=on_done,
            on_error=lambda: self.msg_queue.put(("error", None)),
            output_format=fmt,
            output_dir=out_dir,
            post_process=self._get_post_settings(),
        )

    def stop(self):
        if not self.runner.is_running:
            return
        msg = "确定要停止当前任务吗？"
        if self.batch_mode.get():
            msg = "确定要停止批量处理吗？\n（当前文件处理完后停止）"
        if messagebox.askyesno("确认", msg):
            if self.batch_mode.get():
                self.runner.batch_stop()
            else:
                self.runner.kill()
            self.msg_queue.put(("log", "⚠ 已请求停止任务。"))

    def open_output(self):
        out_dir = self.output_dir.get().strip()
        if not out_dir or not os.path.isdir(out_dir):
            messagebox.showinfo("提示", "输出目录不存在。")
            return
        try:
            os.startfile(out_dir)
        except OSError as e:
            messagebox.showerror("错误", f"无法打开目录：\n{e}")

    def clear_log(self):
        self.log_text.delete("1.0", "end")

    # ======================== 批量模式辅助 ======================== #

    def _toggle_compare(self):
        if self.compare_mode.get():
            self._compare_row.grid()
        else:
            self._compare_row.grid_remove()

    def _get_model_name(self):
        """从 Combobox 的显示标签映射回模型名。"""
        label = self.model_cb.get()
        return self._model_map.get(label, DEFAULT_MODEL)

    def _get_post_settings(self):
        """获取后处理参数。"""
        if not self.post_enable.get():
            return None
        return {
            "denoise": True,
            "denoise_strength": round(self.post_denoise_val.get(), 2),
            "noise_gate": True,
            "gate_threshold": self.post_gate_val.get(),
            "compress": True,
            "compress_threshold": -18,
            "compress_ratio": 3,
            "gain": 0,
        }

    def _toggle_batch_mode(self):
        if self.batch_mode.get():
            self._single_row.grid_remove()
            self._batch_frame.grid()
            self._refresh_batch_list()
        else:
            self._batch_frame.grid_remove()
            self._single_row.grid()

    def _batch_add_files(self):
        paths = filedialog.askopenfilenames(
            title="选择音频文件（可多选）",
            filetypes=[
                ("音频文件", " ".join(f"*{e}" for e in AUDIO_EXTS)),
                ("所有文件", "*.*"),
            ],
        )
        if paths:
            for p in paths:
                if p not in self.file_list and len(self.file_list) < BATCH_MAX_DISPLAY:
                    self.file_list.append(p)
            self._refresh_batch_list()

    def _batch_add_folder(self):
        path = filedialog.askdirectory(title="选择含音频文件的文件夹")
        if not path:
            return
        added = 0
        for root_dir, _, files in os.walk(path):
            for fname in files:
                if any(fname.lower().endswith(ext) for ext in AUDIO_EXTS):
                    fp = os.path.join(root_dir, fname)
                    if fp not in self.file_list and len(self.file_list) < BATCH_MAX_DISPLAY:
                        self.file_list.append(fp)
                        added += 1
        if added:
            self.log(f"从文件夹添加了 {added} 个音频文件。")
        self._refresh_batch_list()

    def _batch_clear(self):
        self.file_list.clear()
        self._refresh_batch_list()

    def _refresh_batch_list(self):
        self._batch_listbox.delete(0, "end")
        for p in self.file_list:
            self._batch_listbox.insert("end", os.path.basename(p))
        n = len(self.file_list)
        self._batch_count.config(text=f"已选 {n} 个文件" + (
            f"（已达上限 {BATCH_MAX_DISPLAY}）" if n >= BATCH_MAX_DISPLAY else ""))

    # ======================== 环境检查 ======================== #

    def _check_env(self):
        """后台检查 demucs 是否可用。"""
        def on_ok():
            self.msg_queue.put(("env_ok", None))

        def on_bad(err):
            self.msg_queue.put(("env_bad", err))

        DemucsRunner.check_env(on_ok=on_ok, on_bad=on_bad)

    def _check_gpu(self):
        """后台检测 GPU 可用性。"""
        def on_result(info):
            self.msg_queue.put(("gpu_info", info))
        DemucsRunner.get_gpu_info(on_result=on_result)

    def _check_bsrf_env(self):
        """后台检查 BS-RoFormer CLI 是否可用。"""
        def on_ok():
            self.msg_queue.put(("bsrf_ok", None))
        def on_bad(err):
            self.msg_queue.put(("bsrf_bad", err))
        BsRoformerRunner.check_env(on_ok=on_ok, on_bad=on_bad)

    # ======================== 消息队列轮询 ======================== #

    def _poll_queue(self):
        """主线程定时轮询消息队列，分发到 UI 更新。"""
        try:
            while True:
                kind, payload = self.msg_queue.get_nowait()
                if kind == "log":
                    self.log(payload)
                elif kind == "progress":
                    self.progress["value"] = payload
                    self.prog_label.config(
                        text=f"处理中… {payload:.0f}%",
                        fg=C_PRIMARY,
                    )
                    # 更新 ETA
                    if self._current_audio_duration > 0:
                        model_name = self._get_model_name()
                        eta = DemucsRunner.estimate_remaining(
                            model_name, self._current_audio_duration, payload)
                        self.eta_label.config(text=f"⏱ {eta}")
                elif kind == "done":
                    self.progress["value"] = 100
                    self.prog_label.config(text="完成", fg=C_SUCCESS)
                    self.eta_label.config(text="")
                    self._finish(success=True)
                elif kind == "error":
                    self.prog_label.config(text="出错或已停止", fg=C_DANGER)
                    self._finish(success=False)
                elif kind == "batch_file_start":
                    idx, total, name = payload
                    self.prog_label.config(
                        text=f"处理中… ({idx + 1}/{total}) {name}",
                        fg=C_PRIMARY)
                elif kind == "batch_file_done":
                    idx, total = payload
                    self.log(f"  [{idx + 1}/{total}] ✓ 完成")
                elif kind == "batch_file_error":
                    idx, reason = payload
                    self.log(f"  [{idx + 1}] ✗ 失败：{reason}")
                elif kind == "batch_all_done":
                    self.progress["value"] = 100
                    self.prog_label.config(text="批量处理完成", fg=C_SUCCESS)
                    self._finish(success=True, batch=True)
                elif kind == "env_ok":
                    self.env_ok = True
                    self.status.config(
                        text=f"环境就绪 · {VENV_PY}",
                        fg=C_SUCCESS,
                    )
                    self.log("✓ demucs 环境检查通过，可以开始分离。")
                elif kind == "env_bad":
                    self.env_ok = False
                    self.status.config(
                        text=f"demucs 未就绪 · {VENV_PY}",
                        fg=C_DANGER,
                    )
                    self.log(f"✗ demucs 环境检查失败：{payload}")
                    self.log(
                        "  请在 venv 中安装依赖：\n"
                        "    pip install torch torchaudio --index-url "
                        "https://download.pytorch.org/whl/cpu\n"
                        "    pip install demucs numpy soundfile\n"
                    )
                elif kind == "bsrf_ok":
                    self.bsrf_ok = True
                    self.log("✓ BS-RoFormer 环境检查通过（首次使用需下载模型 ~700MB）。")
                elif kind == "bsrf_bad":
                    self.bsrf_ok = False
                    self.log(f"⚠ BS-RoFormer 不可用：{payload}")
                elif kind == "compare_phase1_done":
                    # 模型 A 完成，启动模型 B
                    self.log("")
                    self.log("--- 模型 B 开始 ---")
                    self._compare_phase = 2
                    self.progress["value"] = 0
                    self.prog_label.config(text="对比模式：模型 B 处理中…",
                                           fg=C_PRIMARY)
                    in_path = self.input_file.get().strip()
                    out_dir = self.output_dir.get().strip()
                    model_b_label = self._compare_cb.get()
                    model_b = self._compare_model_map.get(model_b_label, DEFAULT_MODEL)
                    post = self._get_post_settings()
                    cmd_b = self.runner.build_command(
                        in_path, out_dir, model_b, mode, shifts)
                    self.log(f">>> 模型 B ({model_b})：{' '.join(cmd_b[1:])}")
                    self.runner.run(
                        cmd_b,
                        on_log=lambda msg: self.msg_queue.put(("log", msg)),
                        on_progress=lambda pct:
                            self.msg_queue.put(("progress", pct)),
                        on_done=lambda:
                            self.msg_queue.put(("compare_all_done", None)),
                        on_error=lambda:
                            self.msg_queue.put(("compare_error", "B")),
                        output_format=fmt, output_dir=out_dir,
                        post_process=post,
                    )
                elif kind == "compare_all_done":
                    self.progress["value"] = 100
                    self.prog_label.config(text="对比完成", fg=C_SUCCESS)
                    self.eta_label.config(text="")
                    self._compare_phase = 0
                    self._finish(success=True)
                    self.log("")
                    self.log("✓ 对比完成！对比结果：")
                    self.log(f"  {out_dir}/{model}/")
                    self.log(f"  {out_dir}/{model_b_label}/")
                elif kind == "compare_error":
                    which = payload
                    self.prog_label.config(text=f"对比出错（模型 {which}）",
                                           fg=C_DANGER)
                    self._compare_phase = 0
                    self._finish(success=False)
                elif kind == "gpu_info":
                    info = payload
                    self.gpu_mode = info["mode"]
                    device = info["device"][:60]
                    gpu_tag = "⚡ GPU" if info["cuda"] else "CPU"
                    self.status.config(
                        text=f"{gpu_tag}: {device}" +
                             (f"  ·  Demucs: {VENV_PY}" if self.env_ok else ""),
                        fg=C_SUCCESS if info["cuda"] else C_TEXT_DIM,
                    )
                    self.log(f"硬件环境：{gpu_tag} — {device}")
        except queue.Empty:
            pass
        self.root.after(POLL_INTERVAL_MS, self._poll_queue)

    # ======================== 日志 ======================== #

    def log(self, msg):
        ts = datetime.now().strftime("%H:%M:%S")
        self.log_text.insert("end", f"[{ts}] {msg}\n")
        self.log_text.see("end")

    # ======================== 状态管理 ======================== #

    def _set_running_state(self, running):
        """切换运行态按钮状态。"""
        state_map = {
            "start": "disabled" if running else "normal",
            "stop": "normal" if running else "disabled",
            "browse": "disabled" if running else "normal",
            "model": "disabled" if running else "readonly",
        }
        self.btn_start.config(state=state_map["start"])
        self.btn_stop.config(state=state_map["stop"])
        self.btn_browse_in.config(state=state_map["browse"])
        self.btn_browse_out.config(state=state_map["browse"])
        self.model_cb.config(state=state_map["model"])
        # 禁用批量模式切换和文件操作
        for child in self.root.winfo_children():
            for widget in child.winfo_children():
                if isinstance(widget, ttk.Checkbutton):
                    try:
                        widget.config(state="disabled" if running else "normal")
                    except tk.TclError:
                        pass

    def _finish(self, success, batch=False):
        self._set_running_state(False)
        if success:
            out_dir = self.output_dir.get()
            model_name = self._get_model_name()
            if batch:
                self.log("")
                self.log(f"批量处理完成。输出目录：{out_dir}")
            elif model_name == BS_RF_MODEL_ID:
                # BS-RoFormer 输出结构：{out_dir}/{文件名}/{stem}.wav
                in_file = os.path.splitext(
                    os.path.basename(self.input_file.get()))[0]
                self.log(f"输出目录：{os.path.join(out_dir, in_file)}")
                self.log("(六轨：vocals/drums/bass/guitar/piano/other + instrumental)")
                self.log("")
            else:
                self.log("输出目录（按 模型名/音轨名/ 分轨存放）：")
                self.log(f"  {os.path.join(out_dir, model_name)}")
                self.log("")
