# -*- coding: utf-8 -*-
r"""
Web 服务 — Flask REST API + 简易 Web 前端。

启动方式：
    python src/web_server.py
或：
    cd <仓库根>
    venv\Scripts\python.exe src/web_server.py

端点：
    GET  /                     Web 前端
    POST /api/separate         提交分离任务
    GET  /api/status/<task_id>  查询任务状态
    GET  /api/download/<task_id>/<filename>  下载结果
    GET  /api/models           列出可用模型
"""

import os
import sys
import uuid
import json
import shutil
import threading
import tempfile
import zipfile
import io
import time

# 确保项目根在 sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask, request, jsonify, send_file, render_template_string
from src.config import MODELS, DEFAULT_MODEL, VENV_PY, AUDIO_EXTS
from src.demucs_runner import DemucsRunner
from src.post_processor import DEFAULT_POST_SETTINGS, apply_post_chain

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 500MB 上传限制

# 全局任务存储
_tasks = {}
_TASK_LOCK = threading.Lock()

OUTPUT_ROOT = os.path.join(os.path.dirname(os.path.dirname(__file__)), "web_outputs")
os.makedirs(OUTPUT_ROOT, exist_ok=True)


# HTML 模板
WEB_HTML = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>音频分离工具 — Web</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:"Microsoft YaHei UI",sans-serif;background:#f4f5f7;color:#1f2329;
     max-width:680px;margin:40px auto;padding:20px}
h1{font-size:22px;margin-bottom:8px}
.sub{color:#6b7280;font-size:13px;margin-bottom:24px}
.card{background:#fff;border:1px solid #e2e5ea;border-radius:8px;padding:20px;margin-bottom:16px}
.card h2{font-size:14px;margin-bottom:12px}
input,select,button{font-size:14px;padding:8px 12px;border:1px solid #e2e5ea;border-radius:6px}
input[type="file"]{width:100%}
select{width:100%}
button{background:#2563eb;color:#fff;border:none;cursor:pointer;width:100%;font-weight:bold}
button:hover{background:#1d4ed8}
button:disabled{background:#9ca3af;cursor:not-allowed}
.row{display:flex;gap:10px;margin-top:10px}
.row>*{flex:1}
.status{font-size:13px;padding:10px;border-radius:6px;margin-top:10px}
.status.pending{background:#fef3c7;color:#92400e}
.status.processing{background:#dbeafe;color:#1e40af}
.status.done{background:#d1fae5;color:#065f46}
.status.error{background:#fee2e2;color:#991b1b}
.result{margin-top:10px}
.result a{display:block;padding:4px 0;color:#2563eb}
.footer{text-align:center;color:#9ca3af;font-size:12px;margin-top:30px}
</style>
</head>
<body>
<h1>🎵 音频分离工具</h1>
<p class="sub">基于 Meta Demucs · 上传音频，提取人声/伴奏/多轨</p>

<div class="card">
  <h2>上传音频文件</h2>
  <form id="uploadForm">
    <input type="file" id="audioFile" accept=".mp3,.wav,.flac,.m4a,.ogg,.wma,.aac"
           required>
    <div class="row">
      <select id="model">
        {% for m in models %}
        <option value="{{ m[0] }}" {% if m[0] == default_model %}selected{% endif %}>
          {{ m[1] }}
        </option>
        {% endfor %}
      </select>
      <select id="mode">
        <option value="two">人声/伴奏（二轨）</option>
        <option value="four">鼓/贝斯/人声/其他（四轨）</option>
      </select>
    </div>
    <div class="row" style="margin-top:8px">
      <button type="submit">▶ 开始分离</button>
    </div>
  </form>
</div>

<div id="taskArea"></div>

<div class="footer">音频分离工具 Web 版 · 基于开源 Demucs 引擎</div>

<script>
const form = document.getElementById('uploadForm');
const taskArea = document.getElementById('taskArea');

form.addEventListener('submit', async (e) => {
  e.preventDefault();
  const file = document.getElementById('audioFile').files[0];
  if (!file) return alert('请选择文件');

  const fd = new FormData();
  fd.append('file', file);
  fd.append('model', document.getElementById('model').value);
  fd.append('mode', document.getElementById('mode').value);
  fd.append('shifts', '2');

  const btn = form.querySelector('button');
  btn.disabled = true; btn.textContent = '上传中…';

  try {
    const resp = await fetch('/api/separate', {method:'POST', body:fd});
    const data = await resp.json();
    if (data.error) { alert(data.error); btn.disabled=false; btn.textContent='▶ 开始分离'; return; }
    pollTask(data.task_id);
  } catch(err) {
    alert('上传失败：' + err.message);
    btn.disabled = false; btn.textContent = '▶ 开始分离';
  }
});

function pollTask(taskId) {
  taskArea.innerHTML = '<div class="status pending">任务已提交，等待处理…</div>';
  const interval = setInterval(async () => {
    try {
      const resp = await fetch('/api/status/' + taskId);
      const data = await resp.json();
      renderTask(data);
      if (data.status === 'done' || data.status === 'error') {
        clearInterval(interval);
        document.querySelector('button').disabled = false;
        document.querySelector('button').textContent = '▶ 开始分离';
      }
    } catch(e) { clearInterval(interval); }
  }, 2000);
}

function renderTask(data) {
  let cls = data.status === 'done' ? 'done' :
            data.status === 'error' ? 'error' :
            data.status === 'processing' ? 'processing' : 'pending';
  let html = `<div class="status ${cls}">`;
  if (data.status === 'pending') html += '⏳ 队列中…';
  else if (data.status === 'processing') html += `🔄 处理中… ${data.progress||0}%`;
  else if (data.status === 'done') {
    html += '✅ 分离完成！<div class="result">';
    (data.files||[]).forEach(f => {
      html += `<a href="/api/download/${data.task_id}/${f}" download>📥 ${f}</a>`;
    });
    html += '</div>';
  } else html += '❌ 处理失败：' + (data.message||'未知错误');
  html += '</div>';
  taskArea.innerHTML = html;
}
</script>
</body>
</html>
"""


# ==================== 路由 ====================

@app.route("/")
def index():
    return render_template_string(
        WEB_HTML, models=MODELS, default_model=DEFAULT_MODEL)


@app.route("/api/models")
def api_models():
    return jsonify([{"id": m[0], "label": m[1]} for m in MODELS])


@app.route("/api/separate", methods=["POST"])
def api_separate():
    if "file" not in request.files:
        return jsonify({"error": "未上传文件"}), 400
    f = request.files["file"]
    if not f.filename:
        return jsonify({"error": "文件名为空"}), 400

    ext = os.path.splitext(f.filename)[1].lower()
    if ext not in AUDIO_EXTS:
        return jsonify({"error": f"不支持的格式：{ext}"}), 400

    # 保存上传文件
    task_id = str(uuid.uuid4())[:8]
    task_dir = os.path.join(OUTPUT_ROOT, task_id)
    os.makedirs(task_dir, exist_ok=True)
    input_path = os.path.join(task_dir, f.filename)
    f.save(input_path)

    # 读取参数
    model = request.form.get("model", DEFAULT_MODEL)
    mode = request.form.get("mode", "two")
    shifts = int(request.form.get("shifts", 2))

    # 注册任务
    task = {
        "task_id": task_id,
        "status": "pending",
        "progress": 0,
        "message": "",
        "files": [],
        "created": time.time(),
    }
    with _TASK_LOCK:
        _tasks[task_id] = task

    # 启动后台处理
    def process():
        with _TASK_LOCK:
            _tasks[task_id]["status"] = "processing"

        runner = DemucsRunner()
        cmd = runner.build_command(input_path, task_dir, model, mode, shifts)

        def on_log(msg):
            pass  # 不在 web 端显示详细日志

        def on_progress(pct):
            with _TASK_LOCK:
                if task_id in _tasks:
                    _tasks[task_id]["progress"] = int(pct)

        done_event = threading.Event()
        error_event = threading.Event()

        def on_done():
            done_event.set()

        def on_error():
            error_event.set()

        runner.run(
            cmd,
            on_log=on_log, on_progress=on_progress,
            on_done=on_done, on_error=on_error,
            output_format="wav", output_dir=task_dir,
            post_process=DEFAULT_POST_SETTINGS,
        )

        # 等待完成
        done_event.wait(timeout=600)
        if error_event.is_set() or runner.is_running:
            with _TASK_LOCK:
                _tasks[task_id]["status"] = "error"
                _tasks[task_id]["message"] = "分离失败或超时"
            return

        # 收集输出文件
        output_files = []
        for root, _, files in os.walk(task_dir):
            for fn in files:
                if fn.endswith(".wav") and fn != os.path.basename(input_path):
                    rel = os.path.relpath(os.path.join(root, fn), task_dir)
                    output_files.append(rel)

        with _TASK_LOCK:
            _tasks[task_id]["status"] = "done"
            _tasks[task_id]["files"] = output_files
            _tasks[task_id]["progress"] = 100

    threading.Thread(target=process, daemon=True).start()

    return jsonify({"task_id": task_id, "status": "pending"})


@app.route("/api/status/<task_id>")
def api_status(task_id):
    with _TASK_LOCK:
        task = _tasks.get(task_id)
    if not task:
        return jsonify({"error": "任务不存在"}), 404
    return jsonify(task)


@app.route("/api/download/<task_id>/<path:filename>")
def api_download(task_id, filename):
    file_path = os.path.join(OUTPUT_ROOT, task_id, filename)
    if not os.path.isfile(file_path):
        return jsonify({"error": "文件不存在"}), 404
    return send_file(file_path, as_attachment=True,
                     download_name=os.path.basename(filename))


# ==================== 启动 ====================

def main():
    import argparse
    parser = argparse.ArgumentParser(description="音频分离 Web 服务")
    parser.add_argument("--port", type=int, default=8080, help="服务端口")
    parser.add_argument("--host", default="127.0.0.1", help="绑定地址")
    args = parser.parse_args()

    print(f"音频分离 Web 服务启动：http://{args.host}:{args.port}")
    print(f"输出目录：{OUTPUT_ROOT}")
    app.run(host=args.host, port=args.port, debug=False)


if __name__ == "__main__":
    main()
