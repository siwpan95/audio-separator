# -*- coding: utf-8 -*-
"""
BS-RoFormer 运行器 — 通过 bs-roformer-infer CLI 执行音频分离。

BS-RoFormer 是当前 SOTA（Vocals SDR ~11.9 dB），使用频段分割
+ RoPE Transformer 架构，比 Demucs 的人声分离质量高约 3 dB。

输出六轨：vocals / drums / bass / guitar / piano / other + instrumental
"""

import os
import re
import shutil
import tempfile
import subprocess
import threading

from .config import VENV_PY, PROJECT_DIR


# bs-roformer-infer CLI 路径
_BS_RF_CLI = os.path.join(PROJECT_DIR, "venv", "Scripts", "bs-roformer-infer.exe")

# Torch DLL 路径（嵌入式 Python venv 需要）
_TORCH_LIB = os.path.join(PROJECT_DIR, "venv", "Lib", "site-packages", "torch", "lib")

# 可用模型
BS_RF_MODELS = [
    ("roformer-model-bs-roformer-sw-by-jarredou",
     "BS-RoFormer-SW (六轨：人声/鼓/贝斯/吉他/钢琴/其他，推荐)"),
]

DEFAULT_BS_RF_MODEL = BS_RF_MODELS[0][0]


def _subprocess_env():
    """构造子进程环境变量，确保 torch DLL 可被找到。"""
    env = os.environ.copy()
    paths = env.get("PATH", "")
    if _TORCH_LIB not in paths:
        env["PATH"] = _TORCH_LIB + os.pathsep + paths
    if "BS_ROFORMER_MODELS_PATH" not in env:
        env["BS_ROFORMER_MODELS_PATH"] = os.path.join(
            PROJECT_DIR, "venv", "models", "bs_roformer")
    return env


class BsRoformerRunner:
    """封装 BS-RoFormer CLI 的全部交互逻辑。"""

    def __init__(self):
        self.proc = None
        self.worker = None
        self.is_running = False
        self._tmpdir = None

    # ------------------------ 命令构造 ------------------------ #

    @staticmethod
    def build_command(in_path, out_dir, model=DEFAULT_BS_RF_MODEL):
        """构造 bs-roformer-infer CLI 命令列表。

        CLI 要求 --input_folder 参数，因此将输入文件复制到临时目录。
        实际执行时由 run() 方法处理临时目录创建和清理。

        Args:
            in_path:  输入音频文件路径
            out_dir:  输出目录
            model:    模型 slug（默认 BS-RoFormer-SW）
        Returns:
            (str temp_dir, list[str] cmd)
        """
        tmpdir = tempfile.mkdtemp(prefix="bsrf_")
        # 复制文件到临时目录
        shutil.copy2(in_path, os.path.join(tmpdir, os.path.basename(in_path)))

        cmd = [
            VENV_PY, _BS_RF_CLI,
            "--model", model,
            "--store_dir", out_dir,
            "--input_folder", tmpdir,
        ]
        return tmpdir, cmd

    # ------------------------ 子进程执行 ------------------------ #

    def run(self, in_path, out_dir, model=DEFAULT_BS_RF_MODEL,
            on_log=None, on_progress=None, on_done=None, on_error=None):
        """后台线程中运行 BS-RoFormer。

        Args:
            in_path:      输入音频文件路径
            out_dir:      输出目录
            model:        模型 slug
            on_log:       callback(str)
            on_progress:  callback(float)
            on_done:      callback()
            on_error:     callback()
        """
        self.is_running = True
        self.worker = threading.Thread(
            target=self._run_worker,
            args=(in_path, out_dir, model,
                  on_log, on_progress, on_done, on_error),
            daemon=True,
        )
        self.worker.start()

    def _run_worker(self, in_path, out_dir, model,
                    on_log, on_progress, on_done, on_error):
        tmpdir = None
        try:
            if on_log:
                on_log("BS-RoFormer 准备中…")
                on_log("  (首次使用需下载模型 ~700MB，请耐心等待)")
                on_log("")

            tmpdir, cmd = self.build_command(in_path, out_dir, model)
            self._tmpdir = tmpdir

            creationflags = (subprocess.CREATE_NEW_PROCESS_GROUP
                             if os.name == "nt" else 0)

            if on_log:
                on_log(f">>> 启动 BS-RoFormer：{os.path.basename(in_path)}")

            self.proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                env=_subprocess_env(),
                creationflags=creationflags,
            )

            for line in self.proc.stdout:
                self._parse_output(line, on_log, on_progress)

            ret = self.proc.wait()
            if ret == 0:
                if on_log:
                    on_log("✓ BS-RoFormer 分离完成！")
                if on_done:
                    on_done()
            else:
                if on_log:
                    on_log(f"✗ 进程退出码：{ret}")
                if on_error:
                    on_error()
        except FileNotFoundError:
            if on_log:
                on_log(f"✗ 找不到解释器或 CLI：{_BS_RF_CLI}")
            if on_error:
                on_error()
        except Exception as e:
            if on_log:
                on_log(f"✗ 发生异常：{e}")
            if on_error:
                on_error()
        finally:
            self.proc = None
            self.is_running = False
            # 清理临时目录
            if tmpdir and os.path.isdir(tmpdir):
                try:
                    shutil.rmtree(tmpdir, ignore_errors=True)
                except Exception:
                    pass
            self._tmpdir = None

    # ------------------------ 输出解析 ------------------------ #

    @staticmethod
    def _parse_output(line, on_log, on_progress):
        text = line.rstrip("\n")
        if not text.strip():
            return

        # 尝试提取百分比进度
        m = re.search(r'(\d+(?:\.\d+)?)\s*%', text)
        if m:
            pct = float(m.group(1))
            if on_progress:
                on_progress(min(pct, 100.0))
            return

        # 非进度行作为日志
        if on_log:
            on_log(text.strip())

    # ------------------------ 环境检查 ------------------------ #

    @staticmethod
    def check_env(on_ok=None, on_bad=None):
        """后台检查 BS-RoFormer CLI 是否可用。"""
        def worker():
            try:
                creationflags = (subprocess.CREATE_NEW_PROCESS_GROUP
                                 if os.name == "nt" else 0)
                r = subprocess.run(
                    [VENV_PY, _BS_RF_CLI, "--help"],
                    capture_output=True, text=True, timeout=20,
                    encoding="utf-8", errors="replace",
                    env=_subprocess_env(),
                    creationflags=creationflags,
                )
                if r.returncode == 0:
                    if on_ok:
                        on_ok()
                else:
                    err = (r.stderr or r.stdout or "").strip()
                    if on_bad:
                        on_bad(err[:300])
            except Exception as e:
                if on_bad:
                    on_bad(str(e)[:300])

        threading.Thread(target=worker, daemon=True).start()

    # ------------------------ 进程终止 ------------------------ #

    def kill(self):
        if self.proc is None:
            return
        pid = self.proc.pid
        try:
            if os.name == "nt":
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(pid)],
                    capture_output=True)
            else:
                self.proc.terminate()
        except Exception:
            try:
                self.proc.kill()
            except Exception:
                pass
