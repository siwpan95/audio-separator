# -*- coding: utf-8 -*-
"""
Demucs 运行器 — 命令构造、子进程执行、输出解析、环境检查、
          格式转换（WAV→FLAC）、批量处理。

与 UI 完全解耦：通过回调函数通知进度 / 日志 / 完成 / 出错。
UI 层只需实例化 DemucsRunner 并传入回调即可。
"""

import os
import re
import glob
import json
import subprocess
import threading

import soundfile as sf

from .config import VENV_PY, ENV_CHECK_TIMEOUT, PROJECT_DIR

# 嵌入式 Python venv 需要手动将 torch/lib 加入 DLL 搜索路径
_TORCH_LIB = os.path.join(PROJECT_DIR, "venv", "Lib", "site-packages", "torch", "lib")


def _subprocess_env():
    """构造子进程环境变量，确保 torch DLL 可被找到。"""
    env = os.environ.copy()
    paths = env.get("PATH", "")
    if _TORCH_LIB not in paths:
        env["PATH"] = _TORCH_LIB + os.pathsep + paths
    return env


class DemucsRunner:
    """封装 demucs CLI 的全部交互逻辑。"""

    def __init__(self):
        self.proc = None          # subprocess.Popen 句柄
        self.worker = None        # 工作线程
        self.is_running = False   # 是否正在运行

    # ------------------------ 命令构造 ------------------------ #

    @staticmethod
    def build_command(in_path, out_dir, model, mode, shifts):
        """构造 demucs CLI 命令列表。

        Args:
            in_path:  输入音频文件路径
            out_dir:   输出目录
            model:     模型名（如 htdemucs）
            mode:      分离模式 "two" | "four"
            shifts:    位移次数（0-10）
        Returns:
            list[str] 命令参数列表（首元素为解释器路径）
        """
        cmd = [
            VENV_PY, "-u", "-m", "demucs",
            "--name", model,
            "-o", out_dir,
            "--shifts", str(shifts),
            "--filename", "{track}/{stem}.{ext}",
        ]
        if mode == "two":
            cmd += ["--two-stems", "vocals"]
        cmd.append(in_path)
        return cmd

    @staticmethod
    def _extract_model_from_cmd(cmd):
        """从命令列表中提取模型名（在 --name 之后）。"""
        try:
            idx = cmd.index("--name")
            return cmd[idx + 1]
        except (ValueError, IndexError):
            return "htdemucs"

    # ------------------------ 子进程执行 ------------------------ #

    def run(self, cmd, on_log=None, on_progress=None,
            on_done=None, on_error=None, output_format=None, output_dir=None,
            post_process=None):
        """在后台线程中运行 demucs 子进程。

        Args:
            cmd:           build_command() 返回的命令列表
            on_log:        callback(str)
            on_progress:   callback(float)
            on_done:       callback()
            on_error:      callback()
            output_format: "wav"|"flac"
            output_dir:    str
            post_process:  dict — 后处理参数（None=不后处理）
        """
        self.is_running = True
        self.worker = threading.Thread(
            target=self._run_subprocess,
            args=(cmd, on_log, on_progress, on_done, on_error,
                  output_format, output_dir, post_process),
            daemon=True,
        )
        self.worker.start()

    def _run_subprocess(self, cmd, on_log, on_progress, on_done, on_error,
                        output_format=None, output_dir=None, post_process=None):
        """工作线程主体：运行 demucs 并解析输出。"""
        try:
            creationflags = 0
            if os.name == "nt":
                creationflags = subprocess.CREATE_NEW_PROCESS_GROUP

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

            # demucs 的 tqdm 进度走 stderr（已合并到 stdout）
            for line in self.proc.stdout:
                self._parse_output(line, on_log, on_progress)

            ret = self.proc.wait()
            if ret == 0:
                # 确定音轨目录
                model = self._extract_model_from_cmd(cmd)
                input_name = os.path.splitext(os.path.basename(cmd[-1]))[0]
                stem_dir = os.path.join(output_dir or "", model, input_name)
                # 格式转换
                if output_format and output_dir:
                    self.convert_format(stem_dir, output_format, on_log=on_log)
                # 后处理（通过 venv 子进程执行，因为依赖在 venv 中）
                if post_process:
                    self._run_post_processing(stem_dir, post_process, on_log)
                if on_log:
                    on_log("✓ 分离完成！")
                if on_done:
                    on_done()
            else:
                if on_log:
                    on_log(f"✗ 进程退出码：{ret}")
                if on_error:
                    on_error()
        except FileNotFoundError:
            if on_log:
                on_log(f"✗ 找不到解释器：{VENV_PY}\n"
                       "  请确认 venv 已创建并安装 demucs。")
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

    # ------------------------ 输出解析 ------------------------ #

    @staticmethod
    def _parse_output(line, on_log, on_progress):
        """解析 demucs / tqdm 输出行，提取进度或转发日志。

        tqdm 进度条用 \\r 就地刷新，一行内可能含多个进度快照，取最后一段。
        形如 " 45%|████▌  | 3.20/7.23 [00:12<00:15, ...]"
        """
        text = line.rstrip("\n")
        if not text.strip():
            return

        last = text.split("\r")[-1].strip()
        m = re.search(r'(\d+(?:\.\d+)?)\s*%', last)
        if m:
            pct = float(m.group(1))
            if on_progress:
                on_progress(min(pct, 100.0))
            return

        msg = last if last else text.strip()
        if msg and on_log:
            on_log(msg)

    # ------------------------ 环境检查 ------------------------ #

    @staticmethod
    def check_env(on_ok=None, on_bad=None):
        """后台检查 demucs 是否可用（不阻塞调用线程）。

        Args:
            on_ok:  callback()  — 环境就绪
            on_bad: callback(str) — 环境不可用，传入错误信息
        """
        def worker():
            try:
                creationflags = (subprocess.CREATE_NEW_PROCESS_GROUP
                                 if os.name == "nt" else 0)
                r = subprocess.run(
                    [VENV_PY, "-m", "demucs", "--list-models"],
                    capture_output=True, text=True,
                    timeout=ENV_CHECK_TIMEOUT,
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

    @staticmethod
    def get_gpu_info(on_result=None):
        """后台检测 GPU 可用性（在 venv 环境中运行 torch.cuda）。

        Args:
            on_result: callback(dict) — 结果字典 {cuda: bool, device: str, mode: str}
        """
        def worker():
            try:
                creationflags = (subprocess.CREATE_NEW_PROCESS_GROUP
                                 if os.name == "nt" else 0)
                r = subprocess.run(
                    [VENV_PY, "-c",
                     "import torch; "
                     "print('CUDA:' + str(torch.cuda.is_available())); "
                     "print('DEVICE:' + (torch.cuda.get_device_name(0) "
                     "if torch.cuda.is_available() else 'CPU'))"],
                    capture_output=True, text=True,
                    timeout=15, encoding="utf-8", errors="replace",
                    env=_subprocess_env(),
                    creationflags=creationflags,
                )
                lines = r.stdout.strip().split("\n")
                cuda = "True" in lines[0] if lines else False
                device = lines[1].split(":", 1)[1].strip() if len(lines) > 1 else "CPU"
                if on_result:
                    on_result({"cuda": cuda, "device": device,
                               "mode": "GPU" if cuda else "CPU only"})
            except Exception as e:
                if on_result:
                    on_result({"cuda": False, "device": f"检测失败：{e}",
                               "mode": "CPU only"})

        threading.Thread(target=worker, daemon=True).start()

    @staticmethod
    def get_audio_duration(file_path):
        """快速获取音频时长（秒），只读文件头，不加载数据。

        Returns:
            float — 音频时长秒数，失败返回 0
        """
        try:
            info = sf.info(file_path)
            return info.duration
        except Exception:
            return 0

    @staticmethod
    def estimate_remaining(model, audio_duration, progress_pct):
        """根据模型速度和当前进度估算剩余时间。

        Args:
            model:           模型名
            audio_duration:  音频时长秒数
            progress_pct:    当前进度 0-100
        Returns:
            str — 预估剩余时间文本，如 "约 2 分 30 秒"
        """
        from .config import PROCESSING_SPEED
        speed = PROCESSING_SPEED.get(model, 0.04)
        if speed <= 0:
            return "计算中…"
        total_expected = audio_duration / speed  # 预期总耗时秒数
        remaining = total_expected * (1 - progress_pct / 100)
        if remaining < 5:
            return "即将完成"
        mins = int(remaining // 60)
        secs = int(remaining % 60)
        if mins > 0:
            return f"约 {mins} 分 {secs} 秒"
        return f"约 {secs} 秒"

    # ------------------------ 后处理（venv 子进程） ------------------------ #

    @staticmethod
    def _run_post_processing(audio_dir, settings, on_log):
        """通过 venv 子进程运行后处理。

        post_processor 依赖（noisereduce/pedalboard）仅安装在 venv 中，
        GUI 进程（F:/Python314）中没有，因此必须通过子进程执行。
        """
        if on_log:
            on_log("")
            on_log(">>> 开始后处理…")
        try:
            srcdir = os.path.dirname(os.path.dirname(__file__))
            settings_s = json.dumps(settings).replace('"', r'\"')
            code = (
                "import sys,json,glob,os\n"
                f"sys.path.insert(0,r'{srcdir}')\n"
                "from src.post_processor import apply_post_chain\n"
                "import json\n"
                f"s=json.loads('{json.dumps(settings)}')\n"
                f"n=apply_post_chain(r'{audio_dir}',s)\n"
                "print(f'POST_OK:{n}')\n"
            )
            creationflags = (subprocess.CREATE_NEW_PROCESS_GROUP
                             if os.name == "nt" else 0)
            r = subprocess.run(
                [VENV_PY, "-c", code],
                capture_output=True, text=True,
                timeout=120, encoding="utf-8", errors="replace",
                env=_subprocess_env(),
                creationflags=creationflags,
            )
            output = (r.stdout or "").strip()
            if "POST_OK:" in output:
                if on_log:
                    on_log("✓ 后处理完成。")
            else:
                err = (r.stderr or output or "未知错误")[:200]
                if on_log:
                    on_log(f"✗ 后处理失败：{err}")
        except Exception as e:
            if on_log:
                on_log(f"✗ 后处理异常：{e}")

    # ------------------------ 进程终止 ------------------------ #

    def kill(self):
        """终止 demucs 子进程（整棵进程树）。"""
        if self.proc is None:
            return
        pid = self.proc.pid
        try:
            if os.name == "nt":
                # taskkill /T /F 杀掉整棵进程树
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(pid)],
                    capture_output=True,
                )
            else:
                self.proc.terminate()
        except Exception:
            try:
                self.proc.kill()
            except Exception:
                pass

    # ------------------------ 格式转换 ------------------------ #

    @staticmethod
    def convert_format(wav_dir, output_format, on_log=None):
        """将 demucs 输出的 WAV 文件转换为目标格式。

        Demucs 始终输出 WAV，本方法在分离完成后将结果转码。

        Args:
            wav_dir:       demucs 输出目录（含模型名/音轨名子目录）
            output_format: "wav" | "flac"
            on_log:        callback(str)
        Returns:
            bool — 是否转换成功
        """
        if output_format == "wav":
            return True  # 无需转换

        if output_format != "flac":
            if on_log:
                on_log(f"⚠ 不支持的输出格式：{output_format}，跳过转换。")
            return False

        wav_files = glob.glob(os.path.join(wav_dir, "**", "*.wav"), recursive=True)
        if not wav_files:
            if on_log:
                on_log("⚠ 未找到 WAV 文件，跳过格式转换。")
            return False

        converted = 0
        failed = 0
        for wav_path in wav_files:
            flac_path = os.path.splitext(wav_path)[0] + ".flac"
            try:
                data, sr = sf.read(wav_path)
                sf.write(flac_path, data, sr, format="FLAC")
                os.remove(wav_path)
                converted += 1
            except Exception as e:
                failed += 1
                if on_log:
                    on_log(f"  ✗ 转换失败：{os.path.basename(wav_path)} — {e}")

        if on_log:
            on_log(f"✓ 格式转换完成：{converted} 个文件 → FLAC"
                   + (f"，{failed} 个失败" if failed else ""))
        return converted > 0

    # ------------------------ 批量处理 ------------------------ #

    def run_batch(self, file_list, out_dir, model, mode, shifts, output_format,
                  on_file_start=None, on_file_done=None, on_file_error=None,
                  on_batch_progress=None, on_log=None, on_all_done=None):
        """批量处理多个文件（在后台线程中逐个处理）。

        Args:
            file_list:        [str] — 输入文件路径列表
            out_dir:          str   — 输出根目录
            model/mode/shifts — 分离参数
            output_format:    "wav" | "flac"
            on_file_start:    callback(int idx, int total, str path)
            on_file_done:     callback(int idx, int total)
            on_file_error:    callback(int idx, str reason)
            on_batch_progress: callback(float overall_pct 0-100)
            on_log:           callback(str msg)
            on_all_done:      callback()
        """
        self.is_running = True
        self.worker = threading.Thread(
            target=self._batch_worker,
            args=(file_list, out_dir, model, mode, shifts, output_format,
                  on_file_start, on_file_done, on_file_error,
                  on_batch_progress, on_log, on_all_done),
            daemon=True,
        )
        self.worker.start()

    def _batch_worker(self, file_list, out_dir, model, mode, shifts,
                      output_format, on_file_start, on_file_done, on_file_error,
                      on_batch_progress, on_log, on_all_done):
        total = len(file_list)
        self._batch_stop = False

        for idx, path in enumerate(file_list):
            if self._batch_stop:
                if on_log:
                    on_log("■ 批量处理已停止。")
                break

            fname = os.path.basename(path)
            if on_file_start:
                on_file_start(idx, total, fname)
            if on_log:
                on_log(f"\n{'─' * 50}")
                on_log(f"处理 ({idx + 1}/{total})：{fname}")
                on_log(f"{'─' * 50}")

            # 构造命令
            cmd = self.build_command(path, out_dir, model, mode, shifts)

            # 同步执行分离（在同一个后台线程中）
            success = False
            error_reason = None
            try:
                creationflags = (subprocess.CREATE_NEW_PROCESS_GROUP
                                 if os.name == "nt" else 0)
                self.proc = subprocess.Popen(
                    cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True, encoding="utf-8", errors="replace",
                    bufsize=1, env=_subprocess_env(),
                    creationflags=creationflags,
                )
                for line in self.proc.stdout:
                    self._parse_output(line, on_log,
                                       lambda pct: self._batch_sub_progress(
                                           idx, total, pct, on_batch_progress))
                ret = self.proc.wait()
                if ret == 0:
                    # 格式转换
                    stem_dir = os.path.join(out_dir, model,
                                            os.path.splitext(fname)[0])
                    self.convert_format(stem_dir, output_format, on_log=on_log)
                    success = True
                else:
                    error_reason = f"进程退出码：{ret}"
            except Exception as e:
                error_reason = str(e)
            finally:
                self.proc = None

            if success:
                if on_log:
                    on_log(f"✓ {fname} 处理完成。")
                if on_file_done:
                    on_file_done(idx, total)
            else:
                if on_log:
                    on_log(f"✗ {fname} 处理失败：{error_reason}")
                if on_file_error:
                    on_file_error(idx, error_reason or "未知错误")

            # 更新整体进度
            if on_batch_progress:
                on_batch_progress(((idx + 1) / total) * 100)

        self.is_running = False
        if on_all_done:
            on_all_done()

    @staticmethod
    def _batch_sub_progress(file_idx, total, sub_pct, on_batch_progress):
        """将单文件子进度映射为整体批量进度。"""
        if on_batch_progress:
            overall = ((file_idx + sub_pct / 100.0) / total) * 100
            on_batch_progress(min(overall, 100.0))

    def batch_stop(self):
        """停止批量处理（处理完当前文件后终止）。"""
        self._batch_stop = True
        self.kill()
