# 音频分离技术调研报告

> 调研时间：2026-08-10  
> 项目：G:\tools\audio\audio_separator  
> 当前方案：Demucs v4 (htdemucs) + tkinter GUI

---

## 一、概述

音频源分离（Audio Source Separation）是将混合音频拆分为独立音轨（人声、鼓、贝斯等）的技术。随着深度学习的发展，分离质量已从 2019 年 Spleeter 的 ~5 dB SDR 提升到 2025 年 BS-RoFormer 的 ~11.9 dB SDR。

本报告基于联网调研，对比当前主流开源方案，并为项目后续增强提供方向建议。

---

## 二、核心模型 / 工具对比

### 2.1 SDR 基准对比表（MUSDB18-HQ 数据集）

| 模型 | 年份 | Vocals SDR | Avg SDR | 特点 |
|------|------|-----------|---------|------|
| Spleeter (4-stems) | 2019 | ~5.5 dB | ~5.0 dB | 速度快，质量低，已停止维护 |
| Demucs v3 (hdemucs) | 2021 | ~7.3 dB | ~7.7 dB | 混合频谱+波形，MDX 挑战赛 |
| htdemucs (v4) | 2022 | ~8.7 dB | ~9.0 dB | **当前项目使用**，平衡质量与速度 |
| htdemucs_ft (v4 微调) | 2023 | ~8.9 dB | ~9.2 dB | 微调版，质量更高但慢 4 倍 |
| mdx_extra | 2021 | ~9.0 dB | ~8.1 dB | 人声分离强，鼓/贝斯弱 |
| BS-RoFormer | 2024-2025 | **~11.9 dB** | **~10.0 dB** | **当前 SOTA**，显著领先 |
| Mel-RoFormer | 2024 | ~11.6 dB | ~9.6 dB | 与 BS-RoFormer 接近 |
| Ensemble (2025.06) | 2025 | ~11.9 dB | — | 多模型集成，最高质量 |

> SDR（Signal-to-Distortion Ratio）越高越好。每提升 1 dB 对应可感知的质量改善。

### 2.2 模型架构演进

```
Spleeter (2019)         Demucs v1/v2 (2019-2020)
  频谱 U-Net               波形 U-Net
  + Wiener 滤波             + 编码器-解码器
  速度快，相位丢失           保留相位，质量更好
       │                         │
       ▼                         ▼
              Demucs v3 "Hybrid" (2021)
              频谱 + 波形双域处理
              SDR ~7.7 dB
                      │
                      ▼
              Demucs v4 "HTDemucs" (2022)     ← 当前项目
              + 跨域 Transformer 注意力
              SDR ~9.0 dB
                      │
                      ▼
              BS-RoFormer (2024)              ← SOTA
              频段分割 + RoPE Transformer
              SDR ~10.0-11.9 dB
```

---

## 三、各方案详细分析

### 3.1 Demucs v4（当前使用）

**架构**：Hybrid Transformer Demucs — 频谱域 + 波形域双路径，内部用跨域 Transformer Encoder（自注意力 + 交叉注意力）。

**预训练模型列表**：

| 模型名 | 说明 | 分轨数 | SDR |
|--------|------|--------|-----|
| `htdemucs` | 默认模型，平衡质量与速度 | 4 | ~9.0 dB |
| `htdemucs_ft` | 微调版，质量更高但慢 4 倍 | 4 | ~9.2 dB |
| `htdemucs_6s` | 实验性六轨（+吉他+钢琴） | 6 | 钢琴质量较差 |
| `hdemucs_mmi` | v3 重训基线 | 4 | ~7.7 dB |
| `mdx` | MDX 挑战赛 A 轨冠军 | 4 | ~7.8 dB |
| `mdx_extra` | 额外训练数据 | 4 | ~8.1 dB |
| `mdx_extra_q` | 量化版，省显存 | 4 | 略低于 mdx_extra |

**优点**：
- 开源（MIT 许可），社区活跃
- 支持 CPU 推理（无需 GPU）
- 支持二轨 / 四轨 / 六轨分离
- `-n htdemucs_ft` + `--shifts` 可进一步提升质量
- 模型自动下载（~80MB），开箱即用

**缺点**：
- CPU 推理较慢（4 分钟歌曲约 90 秒）
- 相比 BS-RoFormer，人声分离 SDR 低 ~3 dB
- htdemucs_6s 的吉他/钢琴质量不佳

**项目当前配置**：
- 模型：htdemucs（默认）
- 模式：二轨（人声/伴奏）
- 位移：1 次
- Python 环境：项目本地 venv（/Python314 基础，torch 2.13+cpu）

### 3.2 BS-RoFormer（当前 SOTA）

**架构**：Band-Split RoFormer — 将音频频谱分割为子带，每个子带用独立的 RoPE（旋转位置编码）Transformer 处理，同时建模细粒度频率特征和长时序结构。

**关键指标**（mvsep.com 基准）：

| 版本 | Vocals SDR | Instrumental SDR |
|------|-----------|-----------------|
| BS Roformer (ver. 2024.02) | 10.42 | 16.73 |
| BS Roformer (ver. 2024.04) | 11.24 | 17.55 |
| BS Roformer (ver. 2024.08) | 11.31 | 17.62 |
| BS Roformer (ver. 2025.07) | **11.89** | **18.20** |

**优点**：
- 人声分离质量最高（比 htdemucs 高 ~3 dB）
- 显著减少金属伪音（metallic artifacts）
- 混响较重的音频处理效果优秀
- 支持六轨分离（BS Roformer SW：vocals/bass/drums/guitar/piano/other）

**缺点**：
- 计算量大，需要 GPU 才能实用
- 尚未有像 Demucs 那样成熟的 CLI 工具
- 部署复杂度高于 Demucs

**集成可行性**：中。需要额外安装 `audio-separator` 包或直接使用 ONNX Runtime 推理。可作为项目的高级模式选项。

### 3.3 Mel-RoFormer

与 BS-RoFormer 类似，但使用梅尔频谱图（更接近人耳感知）。Vocals SDR ~11.6 dB，略低于 BS-RoFormer。参数量更大（94.8M vs 82.8M）。

### 3.4 Spleeter（Deezer）

- 2019 年发布，基于 TensorFlow 的 U-Net
- 速度极快（GPU 上 3 秒 / 4 分钟歌曲）
- 质量最低（Vocals SDR ~5.5 dB）
- **已停止维护**（Deezer 声明 "feature complete"）
- 仅推荐用于快速预览场景

### 3.5 UVR5（Ultimate Vocal Remover 5）

- 非模型，而是**多引擎 GUI 工具**
- 集成 MDX-Net、Demucs、VR Architecture、BS-RoFormer 等
- 一键切换模型，支持参数微调
- Windows/macOS/Linux 全平台
- 适合非技术用户，不适合程序化集成

### 3.6 模型集成方案（Ensemble）

mvsep.com 的 Ensemble 模型组合多个模型输出取最佳：

| 版本 | 组成 | Vocals SDR |
|------|------|-----------|
| 2024.08 | BS Roformer + MelBand Roformer | 11.50 |
| 2024.12 | BS Roformer + MelBand + SCNet XL | 11.61 |
| 2025.06 | BS Roformer (x2) + MelBand (ft) + SCNet XL | **11.93** |

集成方案质量最高但计算量是单模型的 3-4 倍，适合服务器端部署。

---

## 四、项目增强建议

### 4.1 短期（低成本，立即可做）

| # | 建议 | 说明 | 状态 |
|---|------|------|------|
| 1 | **新增 htdemucs_6s 选项** | 已在代码中添加。六轨模式输出吉他/钢琴，适合制作用途 | ✅ 完成 |
| 2 | **增加 htdemucs_ft 推荐提示** | 微调版质量更高，在 UI 上标注「\u2605推荐 质量最高」 | ✅ 完成 |
| 3 | **--shifts 默认值调为 2** | shifts=2 比 shifts=1 质量略好，CPU 增时可接受 | ✅ 完成 |
| 4 | **支持批量处理** | 允许选择多个文件或整个目录，队列依次处理 | ✅ 完成 |
| 5 | **输出格式选项** | 支持 WAV / FLAC 输出格式选择 | ✅ 完成 |

### 4.2 中期（需一定开发量）

| # | 建议 | 说明 | 状态 |
|---|------|------|------|
| 6 | **集成 BS-RoFormer** | 通过 `bs-roformer-infer` 包引入，作为模型列表中「⚡高级」选项。人声 SDR ~11.9 dB，六轨输出 | ✅ 完成 |
| 7 | **GPU 检测与提示** | 检测 CUDA 可用性，状态栏显示 GPU 型号，自动识别 CPU/GPU 模式 | ✅ 完成 |
| 8 | **进度预估** | 基于音频时长 + 模型速度常量估算剩余时间，进度条旁显示 ETA | ✅ 完成 |
| 9 | **预设方案** | 一键选择「卡拉OK模式」「混音制作」「极致质量」等预设；悬停状态栏显示说明 | ✅ 完成 |
| 10 | **后处理链** | 分离后可选去混响（dereverb）、降噪（denoise）等后处理 | 待实现 |

### 4.3 长期（架构升级方向）

| # | 建议 | 说明 | 状态 |
|---|------|------|------|
| 11 | **多模型对比** | 同一文件用两个模型分离，依次执行后对比输出目录 | ✅ 完成 |
| 12 | **模型集成** | 运行 2-3 个模型，取各音轨最优结果组合 | 设计文档（需大量模型特定融合逻辑） |
| 13 | **ONNX 推理后端** | 将模型转为 ONNX 格式，用 ONNX Runtime 推理，减少 PyTorch 依赖体积 | 设计文档（BS-RoFormer 已有 ONNX 可用） |
| 14 | **Web 服务化** | Flask REST API + 简易 Web 前端，支持上传/状态查询/下载 | ✅ 完成 |

---

## 五、BS-RoFormer 集成方案（已实现）

采用 `bs-roformer-infer` 包（纯 PyTorch，CLI 驱动）：

```bash
pip install bs-roformer-infer
```

模型自动下载到 `venv/models/bs_roformer/`，首次使用约 700MB。

**集成方式**：
- `src/bs_roformer_runner.py`：subprocess 调用 CLI
- UI 模型列表中添加 `⚡ BS-RoFormer-SW` 选项
- 引擎自动切换：选择 BS-RoFormer 时使用 BsRoformerRunner
- 输出六轨：vocals/drums/bass/guitar/piano/other + instrumental

**Web 服务**（#14）：
```bash
venv/Scripts/python.exe src/web_server.py --port 8080
```
Flask REST API + 内嵌 Web 前端，支持文件上传、任务队列、进度查询、结果下载。

---

## 六、参考资料

1. **Demucs 官方仓库** — https://github.com/facebookresearch/demucs (MIT License)
2. **Demucs v4 论文** — Rouard et al., "Hybrid Transformers for Music Source Separation", ICASSP 2023
3. **BS-RoFormer 论文** — Lu et al., "High-Fidelity Audio Compression with Latent Diffusion", 2024
4. **audio-separator** — https://github.com/nomadkar.za/audio-separator
5. **UVR5** — https://github.com/Anjok07/ultimatevocalremovergui
6. **mvsep.com 基准测试** — https://mvsep.com/algorithms (SDR 对比数据来源)
7. **Spleeter vs Demucs 对比** — https://stemsplit.io/blog/spleeter-vs-demucs (2026)
8. **PyTorch 2.10 发布说明** — https://pytorch.org/blog/pytorch-2-10-release-blog/ (Python 3.14 支持)
9. **Spleeter (Deezer)** — https://github.com/deezer/spleeter (已停止维护)
