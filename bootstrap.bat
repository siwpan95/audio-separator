@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
if exist "venv\Scripts\python.exe" ( echo [bootstrap] venv 已存在，跳过。 & exit /b 0 )
echo [bootstrap] 检查本机开发环境 venv（离线快速通道）...
REM 2026-09-23 去本地化：离线快速通道改由 AUDIO_SEPARATOR_VENV_SRC 指定（原 G:\tools\audio_separator\venv 已失效）
if defined AUDIO_SEPARATOR_VENV_SRC if exist "%AUDIO_SEPARATOR_VENV_SRC%\Scripts\python.exe" (
  echo [bootstrap] 检测到离线 venv（%AUDIO_SEPARATOR_VENV_SRC%），直接复制（约 1-3 分钟）...
  robocopy "%AUDIO_SEPARATOR_VENV_SRC%" "%~dp0venv" /E /NFL /NDL /NJH /NJS /NP
  if exist "venv\Scripts\python.exe" ( echo [bootstrap] 离线复制完成。 & exit /b 0 )
)
echo [bootstrap] 检查 Python...
where python >nul 2>&1
if errorlevel 1 ( echo [bootstrap] 未找到 python：请安装 Python 3.10+ 并加入 PATH。 & pause & exit /b 1 )
echo [bootstrap] 创建 venv（约 1-2 分钟）...
python -m venv venv
if errorlevel 1 ( echo [bootstrap] venv 创建失败。 & pause & exit /b 1 )
echo [bootstrap] 安装 torch CPU 版（镜像链：阿里云 -> 清华 -> 官方）...
venv\Scripts\python.exe -m pip install --upgrade pip
venv\Scripts\python.exe -m pip install torch torchaudio --index-url https://mirrors.aliyun.com/pytorch-wheels/cpu
if errorlevel 1 venv\Scripts\python.exe -m pip install torch torchaudio --index-url https://mirrors.tuna.tsinghua.edu.cn/pytorch-wheels/cpu
if errorlevel 1 venv\Scripts\python.exe -m pip install torch torchaudio --index-url https://download.pytorch.org/whl/cpu
if errorlevel 1 ( echo [bootstrap] torch 安装失败，请检查网络后重试。 & pause & exit /b 1 )
echo [bootstrap] 安装 demucs / soundfile / numpy / bs-roformer-infer（PyPI 镜像）...
venv\Scripts\python.exe -m pip install demucs soundfile numpy bs-roformer-infer -i https://mirrors.aliyun.com/pypi/simple/
if errorlevel 1 ( echo [bootstrap] 依赖安装失败。 & pause & exit /b 1 )
if not exist models mkdir models
echo [bootstrap] 完成。Demucs 模型首次分离自动下载；BS-RoFormer 模型请按 README 放入 models\。
endlocal
exit /b 0
