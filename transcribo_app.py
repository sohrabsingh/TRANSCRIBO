"""
TRANSCRIBO — Desktop App
All-in-one: pywebview window + faster-whisper backend

Install dependencies:
    pip install faster-whisper pywebview

Build to .exe:
    pip install pyinstaller
    pyinstaller --onefile --windowed --name Transcribo --collect-all faster_whisper --collect-all ctranslate2 --collect-all webview transcribo_app.py
"""

import os
import json
import tkinter as tk
from tkinter import filedialog
import webview
from webview.dom import DOMEventHandler
from faster_whisper import WhisperModel

# ── Globals ────────────────────────────────────────────────────────────────────
_model_cache = {}
_window_ref  = [None]
SUPPORTED = {".wav", ".mp3", ".m4a", ".flac", ".ogg"}


def _notify_js(msg):
    """Send a log message or status update to the UI."""
    if _window_ref[0] is None:
        return
    # Status commands start with __status__:
    if msg.startswith("__status__:"):
        status = msg.split(":", 1)[1]
        _window_ref[0].evaluate_js(f'setStatus("{status}")')
    else:
        safe = msg.replace("'", "\'")
        _window_ref[0].evaluate_js(f"log('{safe}', 'warn')")


def get_model(size, device, compute_type, window=None):
    key = (size, device, compute_type)
    if key not in _model_cache:
        if window:
            window.evaluate_js('onModelDownloadStart(' + json.dumps(size) + ')')

        # If not cached, poll download progress via cache folder size in a thread
        if window and not is_model_cached(size):
            import threading
            import time
            import pathlib

            stop_polling = threading.Event()

            def poll_progress():
                cache_dir = pathlib.Path.home() / '.cache' / 'huggingface' / 'hub'
                dots = 0
                while not stop_polling.is_set():
                    time.sleep(2)
                    dots = (dots + 1) % 4
                    indicator = '.' * (dots + 1)
                    try:
                        # Sum up all partially downloaded files
                        total_mb = sum(
                            f.stat().st_size for f in cache_dir.rglob('*')
                            if f.is_file() and size in str(f)
                        ) / (1024 * 1024)
                        msg = f'Downloading{indicator} {total_mb:.1f} MB received'
                    except Exception:
                        msg = f'Downloading{indicator}'
                    window.evaluate_js(
                        'onModelDownloadProgress(' + json.dumps({'msg': msg}) + ')'
                    )

            t = threading.Thread(target=poll_progress, daemon=True)
            t.start()
            _model_cache[key] = WhisperModel(size, device=device, compute_type=compute_type)
            stop_polling.set()
        else:
            _model_cache[key] = WhisperModel(size, device=device, compute_type=compute_type)

        if window:
            window.evaluate_js('onModelDownloadDone()')

    return _model_cache[key]


def is_model_cached(size):
    """Check if model already exists in local HuggingFace cache."""
    try:
        from huggingface_hub import try_to_load_from_cache
        result = try_to_load_from_cache(
            repo_id=f"Systran/faster-whisper-{size}",
            filename="model.bin"
        )
        return result is not None and result != ""
    except Exception:
        return False


# ── API ────────────────────────────────────────────────────────────────────────
class API:

    def open_files(self) -> dict:
        """Open native file picker via tkinter."""
        try:
            root = tk.Tk()
            root.withdraw()
            root.attributes("-topmost", True)
            paths = filedialog.askopenfilenames(
                title="Select Audio Files",
                filetypes=[
                    ("Audio Files", "*.wav *.mp3 *.m4a *.flac *.ogg"),
                    ("All Files", "*.*"),
                ]
            )
            root.destroy()
            if not paths:
                return {"cancelled": True}
            return {"paths": list(paths)}
        except Exception as e:
            return {"error": str(e)}

    def check_model(self, payload: dict) -> dict:
        """Check if model is already cached locally."""
        try:
            size = payload.get("model", "small")
            return {"cached": is_model_cached(size)}
        except Exception as e:
            return {"cached": False, "error": str(e)}

    def transcribe(self, payload: dict) -> dict:
        """Transcribe audio file given its path on disk."""
        try:
            path         = payload.get("path", "")
            model_size   = payload.get("model", "small")
            device       = payload.get("device", "cpu")
            compute_type = payload.get("compute_type", "int8")

            if not path or not os.path.exists(path):
                return {"error": "File not found: " + path}

            ext = os.path.splitext(path)[1].lower()
            if ext not in SUPPORTED:
                return {"error": "Unsupported file type: " + ext}

            model = get_model(model_size, device, compute_type, window=_window_ref[0])
            segments, info = model.transcribe(path)
            text = " ".join(seg.text.strip() for seg in segments)

            return {
                "text":     text,
                "language": info.language,
                "duration": round(info.duration, 2),
            }
        except Exception as e:
            return {"error": str(e)}

    def save_file(self, payload: dict) -> dict:
        """Save transcript content via native Save dialog."""
        try:
            content      = payload.get("content", "")
            default_name = payload.get("default_name", "transcripts.txt")

            root = tk.Tk()
            root.withdraw()
            root.attributes("-topmost", True)
            path = filedialog.asksaveasfilename(
                title="Save Transcripts",
                initialfile=default_name,
                defaultextension=".txt",
                filetypes=[("Text Files", "*.txt"), ("All Files", "*.*")]
            )
            root.destroy()

            if not path:
                return {"cancelled": True}

            with open(path, "w", encoding="utf-8") as f:
                f.write(content)

            return {"path": path}
        except Exception as e:
            return {"error": str(e)}

    def copy_to_clipboard(self, payload: dict) -> dict:
        """Copy text to system clipboard via subprocess (most reliable on Windows)."""
        try:
            text = payload.get("text", "")
            import subprocess
            proc = subprocess.Popen(
                ['clip'],
                stdin=subprocess.PIPE,
                shell=True
            )
            proc.communicate(input=text.encode('utf-16-le'))
            return {"ok": True}
        except Exception as e:
            return {"error": str(e)}


# ── HTML ───────────────────────────────────────────────────────────────────────
HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Transcribo</title>
<link href="https://fonts.googleapis.com/css2?family=Space+Mono:wght@400;700&family=Syne:wght@400;700;800&display=swap" rel="stylesheet">
<style>
  :root {
    --bg: #0a0a0f;
    --surface: #12121a;
    --panel: #1a1a26;
    --border: #2a2a40;
    --accent: #7cff8b;
    --accent2: #4d9eff;
    --warn: #ff6b6b;
    --text: #e8e8f0;
    --muted: #6a6a88;
    --font-display: 'Syne', sans-serif;
    --font-mono: 'Space Mono', monospace;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    background: var(--bg);
    color: var(--text);
    font-family: var(--font-mono);
    min-height: 100vh;
    overflow-x: hidden;
    user-select: none;
  }
  body::before {
    content: '';
    position: fixed;
    inset: 0;
    background-image:
      linear-gradient(rgba(124,255,139,0.03) 1px, transparent 1px),
      linear-gradient(90deg, rgba(124,255,139,0.03) 1px, transparent 1px);
    background-size: 40px 40px;
    pointer-events: none;
    z-index: 0;
  }
  .app {
    position: relative;
    z-index: 1;
    max-width: 860px;
    margin: 0 auto;
    padding: 36px 24px 80px;
  }
  header {
    display: flex;
    align-items: flex-end;
    justify-content: space-between;
    margin-bottom: 40px;
    padding-bottom: 20px;
    border-bottom: 1px solid var(--border);
  }
  .logo {
    font-family: var(--font-display);
    font-size: 30px;
    font-weight: 800;
    letter-spacing: -1px;
    line-height: 1;
  }
  .logo span {
    display: block;
    font-size: 10px;
    font-weight: 400;
    letter-spacing: 4px;
    text-transform: uppercase;
    color: var(--muted);
    margin-bottom: 4px;
    font-family: var(--font-mono);
  }
  .status-dot { display: flex; align-items: center; gap: 8px; font-size: 11px; color: var(--muted); letter-spacing: 1px; text-transform: uppercase; }
  .dot { width: 8px; height: 8px; border-radius: 50%; background: var(--muted); }
  .dot.ready  { background: var(--accent);  box-shadow: 0 0 8px var(--accent);  animation: pulse 2s infinite; }
  .dot.working{ background: var(--accent2); box-shadow: 0 0 8px var(--accent2); animation: pulse 0.8s infinite; }
  .dot.error  { background: var(--warn);    box-shadow: 0 0 8px var(--warn); }
  @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.4} }

  .config-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; margin-bottom: 20px; }
  .field { display: flex; flex-direction: column; gap: 7px; }
  .field label { font-size: 10px; text-transform: uppercase; letter-spacing: 2px; color: var(--muted); }
  .field select, .field input {
    background: var(--panel); border: 1px solid var(--border);
    color: var(--text); font-family: var(--font-mono); font-size: 12px;
    padding: 9px 12px; border-radius: 6px; outline: none; transition: border-color .2s; appearance: none;
  }
  .field select:focus, .field input:focus { border-color: var(--accent2); }

  .dropzone {
    border: 2px dashed var(--border); border-radius: 12px; padding: 40px 24px;
    text-align: center; cursor: pointer; transition: all .25s; background: var(--surface);
    margin-bottom: 20px; position: relative; overflow: hidden;
  }
  .dropzone::before {
    content:''; position:absolute; inset:0;
    background: radial-gradient(ellipse at 50% 100%, rgba(124,255,139,0.04) 0%, transparent 70%);
    pointer-events: none;
  }
  .dropzone:hover, .dropzone.dragging { border-color: var(--accent); background: #0f1a10; }
  .dropzone-icon { font-size: 32px; margin-bottom: 10px; display: block; }
  .dropzone h3 { font-family: var(--font-display); font-size: 17px; font-weight: 700; margin-bottom: 7px; }
  .dropzone p { color: var(--muted); font-size: 11px; line-height: 1.6; }
  .dropzone p strong { color: var(--accent2); font-weight: 400; }

  .queue-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 10px; }
  .queue-header h4 { font-size: 10px; text-transform: uppercase; letter-spacing: 2px; color: var(--muted); }
  .btn-clear {
    background: none; border: 1px solid var(--border); color: var(--muted);
    font-family: var(--font-mono); font-size: 10px; letter-spacing: 1px; text-transform: uppercase;
    padding: 3px 9px; border-radius: 4px; cursor: pointer; transition: all .2s;
  }
  .btn-clear:hover { border-color: var(--warn); color: var(--warn); }

  .file-list { display: flex; flex-direction: column; gap: 7px; margin-bottom: 20px; max-height: 220px; overflow-y: auto; }
  .file-list::-webkit-scrollbar { width: 4px; }
  .file-list::-webkit-scrollbar-thumb { background: var(--border); border-radius: 2px; }

  .file-item {
    display: flex; align-items: center; gap: 10px;
    background: var(--panel); border: 1px solid var(--border); border-radius: 8px; padding: 9px 12px; transition: border-color .2s;
  }
  .file-item.processing { border-color: var(--accent2); }
  .file-item.done  { border-color: var(--accent); }
  .file-item.error { border-color: var(--warn); }
  .file-icon { font-size: 16px; flex-shrink: 0; }
  .file-info { flex: 1; min-width: 0; }
  .file-name { font-size: 12px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; margin-bottom: 2px; }
  .file-meta { font-size: 10px; color: var(--muted); }
  .file-status { font-size: 10px; text-transform: uppercase; letter-spacing: 1px; padding: 2px 7px; border-radius: 3px; flex-shrink: 0; }
  .status-pending    { color: var(--muted);   border: 1px solid var(--border); }
  .status-processing { color: var(--accent2); border: 1px solid var(--accent2); animation: pulse 1s infinite; }
  .status-done  { color: var(--accent); border: 1px solid var(--accent); }
  .status-error { color: var(--warn);   border: 1px solid var(--warn); }

  .progress-bar { height: 3px; background: var(--border); border-radius: 2px; margin-bottom: 20px; overflow: hidden; display: none; }
  .progress-bar.visible { display: block; }
  .progress-fill { height: 100%; background: linear-gradient(90deg, var(--accent2), var(--accent)); border-radius: 2px; transition: width .4s ease; width: 0%; }

  .action-row { display: flex; gap: 10px; margin-bottom: 28px; }
  .btn-primary {
    flex: 1; background: var(--accent); color: #0a0a0f; border: none;
    font-family: var(--font-mono); font-size: 12px; font-weight: 700; letter-spacing: 2px; text-transform: uppercase;
    padding: 13px 20px; border-radius: 8px; cursor: pointer; transition: all .2s;
  }
  .btn-primary:hover:not(:disabled) { background: #a0ffac; transform: translateY(-1px); box-shadow: 0 4px 20px rgba(124,255,139,.3); }
  .btn-primary:disabled { opacity: .3; cursor: not-allowed; }
  .btn-secondary {
    background: var(--panel); color: var(--text); border: 1px solid var(--border);
    font-family: var(--font-mono); font-size: 12px; letter-spacing: 1px; text-transform: uppercase;
    padding: 13px 18px; border-radius: 8px; cursor: pointer; transition: all .2s;
  }
  .btn-secondary:hover:not(:disabled) { border-color: var(--accent2); color: var(--accent2); }
  .btn-secondary:disabled { opacity: .3; cursor: not-allowed; }

  .log-section { margin-bottom: 28px; }
  .log-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; }
  .log-title { font-size: 10px; text-transform: uppercase; letter-spacing: 2px; color: var(--muted); }
  .log-box {
    background: var(--surface); border: 1px solid var(--border); border-radius: 8px;
    padding: 14px; font-size: 11px; line-height: 1.8; height: 110px; overflow-y: auto; color: var(--muted);
  }
  .log-box::-webkit-scrollbar { width: 4px; }
  .log-box::-webkit-scrollbar-thumb { background: var(--border); }
  .log-line { display: block; }
  .log-line.info    { color: var(--text); }
  .log-line.success { color: var(--accent); }
  .log-line.error   { color: var(--warn); }
  .log-line.warn    { color: #ffd36b; }

  .results-section { display: none; }
  .results-section.visible { display: block; }
  .results-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 14px; }
  .results-title { font-family: var(--font-display); font-size: 19px; font-weight: 700; }
  .results-actions { display: flex; gap: 7px; }

  .transcript-card { background: var(--surface); border: 1px solid var(--border); border-radius: 10px; margin-bottom: 10px; overflow: hidden; transition: border-color .2s; }
  .transcript-card:hover { border-color: var(--accent2); }
  .card-header { display: flex; align-items: center; justify-content: space-between; padding: 11px 14px; background: var(--panel); border-bottom: 1px solid var(--border); cursor: pointer; }
  .card-filename { font-size: 11px; color: var(--accent2); display: flex; align-items: center; gap: 7px; }
  .card-filename::before { content: '◆'; font-size: 7px; }
  .card-toggle { font-size: 10px; color: var(--muted); transition: transform .2s; }
  .card-toggle.open { transform: rotate(180deg); }
  .card-body { padding: 14px; font-size: 13px; line-height: 1.8; color: var(--text); display: none; user-select: text; }
  .card-body.open { display: block; }
  .card-copy {
    display: inline-flex; align-items: center; gap: 5px; margin-top: 10px;
    background: none; border: 1px solid var(--border); color: var(--muted);
    font-family: var(--font-mono); font-size: 10px; letter-spacing: 1px; text-transform: uppercase;
    padding: 3px 9px; border-radius: 4px; cursor: pointer; transition: all .2s;
  }
  .card-copy:hover { border-color: var(--accent2); color: var(--accent2); }
  .hidden { display: none !important; }

  .download-banner {
    display: none;
    background: var(--panel);
    border: 1px solid var(--accent2);
    border-radius: 10px;
    padding: 16px 20px;
    margin-bottom: 20px;
  }
  .download-banner.visible { display: block; }
  .download-title {
    font-size: 11px; text-transform: uppercase; letter-spacing: 2px;
    color: var(--accent2); margin-bottom: 10px;
    display: flex; align-items: center; gap: 8px;
  }
  .download-title::before {
    content: ''; display: inline-block; width: 10px; height: 10px;
    border: 2px solid var(--border); border-top-color: var(--accent2);
    border-radius: 50%; animation: spin .8s linear infinite;
  }
  .download-desc { font-size: 11px; color: var(--muted); margin-bottom: 10px; }
  .download-bar-wrap { height: 4px; background: var(--border); border-radius: 2px; overflow: hidden; }
  .download-bar-fill {
    height: 100%; width: 0%;
    background: linear-gradient(90deg, var(--accent2), var(--accent));
    border-radius: 2px; transition: width .3s ease;
  }
  .download-pct { font-size: 10px; color: var(--muted); margin-top: 6px; text-align: right; }
  @keyframes spin { to { transform: rotate(360deg); } }
  .spinner { display: inline-block; width: 12px; height: 12px; border: 2px solid var(--border); border-top-color: var(--accent2); border-radius: 50%; animation: spin .8s linear infinite; vertical-align: middle; }
</style>
</head>
<body>
<div class="app">
  <header>
    <div class="logo">
      <span>Powered by Faster-Whisper</span>
      TRANSCRIBO
    </div>
    <div class="status-dot">
      <div class="dot ready" id="statusDot"></div>
      <span id="statusText">READY</span>
    </div>
  </header>

  <div class="config-grid">
    <div class="field">
      <label>Model Size</label>
      <select id="modelSize">
        <option value="tiny">tiny — fastest</option>
        <option value="base">base — fast</option>
        <option value="small" selected>small — balanced ✓</option>
        <option value="medium">medium — accurate</option>
        <option value="large-v3">large-v3 — best</option>
      </select>
    </div>
    <div class="field">
      <label>Compute Type</label>
      <select id="computeType">
        <option value="int8" selected>int8 — CPU optimized ✓</option>
        <option value="float16">float16 — GPU</option>
        <option value="float32">float32 — max precision</option>
      </select>
    </div>
    <div class="field">
      <label>Device</label>
      <select id="device">
        <option value="cpu" selected>cpu</option>
        <option value="cuda">cuda (GPU)</option>
      </select>
    </div>
    <div class="field">
      <label>Output Filename</label>
      <input type="text" id="outputFile" value="transcripts.txt" />
    </div>
  </div>

  <div class="download-banner" id="downloadBanner">
    <div class="download-title" id="downloadTitle">Downloading Model</div>
    <div class="download-desc" id="downloadDesc">Please wait while the model is downloaded...</div>
    <div class="download-bar-wrap">
      <div class="download-bar-fill" id="downloadFill"></div>
    </div>
    <div class="download-pct" id="downloadPct">0%</div>
  </div>

  <div class="dropzone" id="dropzone">
    <span class="dropzone-icon">🎙️</span>
    <h3>Drop files here or click to browse</h3>
    <p>supported formats &nbsp;·&nbsp; <strong>.wav .mp3 .m4a .flac .ogg</strong></p>
  </div>

  <div id="queueSection" class="hidden">
    <div class="queue-header">
      <h4 id="queueCount">0 files queued</h4>
      <button class="btn-clear" onclick="clearQueue()">✕ Clear</button>
    </div>
    <div class="file-list" id="fileList"></div>
  </div>

  <div class="progress-bar" id="progressBar">
    <div class="progress-fill" id="progressFill"></div>
  </div>

  <div class="action-row">
    <button class="btn-primary" id="runBtn" onclick="runTranscription()" disabled>▶ &nbsp; TRANSCRIBE</button>
    <button class="btn-secondary" id="exportBtn" onclick="exportTxt()" disabled>⬇ &nbsp; EXPORT .TXT</button>
  </div>

  <div class="log-section">
    <div class="log-header">
      <span class="log-title">// console output</span>
      <button class="btn-clear" onclick="clearLog()">clear</button>
    </div>
    <div class="log-box" id="logBox">
      <span class="log-line">Ready. Drop audio files or click to browse.</span>
    </div>
  </div>

  <div class="results-section" id="resultsSection">
    <div class="results-header">
      <div class="results-title">Transcripts</div>
      <div class="results-actions">
        <button class="btn-secondary" onclick="expandAll()">Expand All</button>
        <button class="btn-secondary" onclick="collapseAll()">Collapse All</button>
      </div>
    </div>
    <div id="transcriptList"></div>
  </div>
</div>

<script>
  let files   = [];
  let results = [];
  const VALID_EXT = ['.wav','.mp3','.m4a','.flac','.ogg'];

  // ── File picker (click) ───────────────────────────────────────────────────
  document.getElementById('dropzone').addEventListener('click', async () => {
    try {
      const res = await window.pywebview.api.open_files();
      if (res.cancelled || !res.paths) return;
      addFilePaths(res.paths);
    } catch(e) {
      log('Could not open file dialog: ' + e.message, 'error');
    }
  });

  // ── Drag and drop visual feedback ─────────────────────────────────────────
  // Actual file paths are injected by Python via evaluate_js('addFilePaths(...)')
  const dz = document.getElementById('dropzone');
  dz.addEventListener('dragover',  e => { e.preventDefault(); dz.classList.add('dragging'); });
  dz.addEventListener('dragleave', () => dz.classList.remove('dragging'));
  dz.addEventListener('drop',      e => { e.preventDefault(); dz.classList.remove('dragging'); });

  // ── Called by Python on drop OR by click picker ───────────────────────────
  function addFilePaths(paths) {
    const fresh = paths.filter(p => {
      const name = p.split(/[/\\\\]/).pop();
      const ext  = '.' + name.split('.').pop().toLowerCase();
      if (!VALID_EXT.includes(ext)) { log('Skipped unsupported: ' + name, 'warn'); return false; }
      if (files.some(f => f.path === p)) { log('Skipped duplicate: ' + name, 'warn'); return false; }
      return true;
    });
    fresh.forEach(p => {
      const name = p.split(/[/\\\\]/).pop();
      files.push({ path: p, name, status: 'pending', id: Math.random().toString(36).slice(2) });
    });
    renderQueue();
    document.getElementById('runBtn').disabled = files.length === 0;
    if (fresh.length) log('Added ' + fresh.length + ' file(s). Total: ' + files.length, 'info');
  }

  // ── Queue ─────────────────────────────────────────────────────────────────
  function renderQueue() {
    const section = document.getElementById('queueSection');
    const list    = document.getElementById('fileList');
    document.getElementById('queueCount').textContent = files.length + ' file' + (files.length !== 1 ? 's' : '') + ' queued';
    if (!files.length) { section.classList.add('hidden'); return; }
    section.classList.remove('hidden');
    const icons = { wav:'🎵', mp3:'🎶', m4a:'🎙️', flac:'💿', ogg:'📻' };
    list.innerHTML = files.map(f => {
      const ext   = f.name.split('.').pop().toLowerCase();
      const label = { pending:'Queued', processing:'Processing', done:'Done', error:'Error' }[f.status];
      return '<div class="file-item ' + (f.status !== 'pending' ? f.status : '') + '" id="item-' + f.id + '">' +
        '<span class="file-icon">' + (icons[ext] || '🔊') + '</span>' +
        '<div class="file-info">' +
          '<div class="file-name">' + f.name + '</div>' +
          '<div class="file-meta">' + ext.toUpperCase() + '</div>' +
        '</div>' +
        '<span class="file-status status-' + f.status + '">' +
          (f.status === 'processing' ? '<span class="spinner"></span>' : label) +
        '</span>' +
      '</div>';
    }).join('');
  }

  function clearQueue() {
    if (files.some(f => f.status === 'processing')) { log('Cannot clear while transcribing.', 'warn'); return; }
    files = [];
    renderQueue();
    document.getElementById('runBtn').disabled = true;
    log('Queue cleared.', 'info');
  }

  // ── Model download callbacks (called by Python via evaluate_js) ─────────────
  function onModelDownloadStart(size) {
    log('Model "' + size + '" not cached — downloading from HuggingFace...', 'warn');
  }

  function onModelDownloadProgress(info) {
    log(info.msg, 'info');
  }

  function onModelDownloadDone() {
    log('Model download complete.', 'success');
  }

  // ── Transcription ─────────────────────────────────────────────────────────
  async function runTranscription() {
    const pending = files.filter(f => f.status === 'pending');
    if (!pending.length) { log('No pending files.', 'warn'); return; }

    const model        = document.getElementById('modelSize').value;
    const compute_type = document.getElementById('computeType').value;
    const device       = document.getElementById('device').value;

    // Check if model is downloaded first
    log('Checking model cache...', 'info');
    try {
      const check = await window.pywebview.api.check_model({ model });
      if (!check.cached) {
        log('Model "' + model + '" is not downloaded. It will be downloaded automatically — this may take several minutes depending on your internet speed.', 'warn');
      } else {
        log('Model "' + model + '" found in cache.', 'success');
      }
    } catch(_) {}

    log('Starting — model: ' + model + ', device: ' + device + ', compute: ' + compute_type, 'info');
    document.getElementById('runBtn').disabled    = true;
    document.getElementById('exportBtn').disabled = true;
    setStatus('working');

    const bar  = document.getElementById('progressBar');
    const fill = document.getElementById('progressFill');
    bar.classList.add('visible');

    let done = 0;
    for (const entry of pending) {
      entry.status = 'processing';
      renderQueue();
      log('Transcribing: ' + entry.name, 'info');

      try {
        const res = await window.pywebview.api.transcribe({
          path: entry.path,
          model,
          device,
          compute_type,
        });

        if (res.error) throw new Error(res.error);

        entry.status = 'done';
        results = results.filter(r => r.name !== entry.name);
        results.push({ name: entry.name, text: res.text, language: res.language, duration: res.duration });
        log('✓ ' + entry.name + ' — ' + (res.language || '?').toUpperCase() + ' · ' + res.duration + 's', 'success');
      } catch (err) {
        entry.status = 'error';
        log('✗ Error on ' + entry.name + ': ' + err.message, 'error');
      }

      done++;
      fill.style.width = (done / pending.length * 100) + '%';
      renderQueue();
    }

    renderResults();
    setStatus('ready');
    document.getElementById('runBtn').disabled    = false;
    document.getElementById('exportBtn').disabled = results.length === 0;
    log('All done. ' + done + ' file(s) processed.', 'success');
    setTimeout(() => bar.classList.remove('visible'), 1200);
  }

  // ── Results ───────────────────────────────────────────────────────────────
  function renderResults() {
    const section = document.getElementById('resultsSection');
    const list    = document.getElementById('transcriptList');
    if (!results.length) { section.classList.remove('visible'); return; }
    section.classList.add('visible');
    list.innerHTML = results.map((r, i) =>
      '<div class="transcript-card">' +
        '<div class="card-header" onclick="toggleCard(' + i + ')">' +
          '<span class="card-filename">' + r.name + '</span>' +
          '<span class="card-toggle open" id="toggle-' + i + '">▼</span>' +
        '</div>' +
        '<div class="card-body open" id="body-' + i + '">' + escHtml(r.text) +
          '<br><button class="card-copy" onclick="copyText(' + i + ', event)">⎘ Copy</button>' +
        '</div>' +
      '</div>'
    ).join('');
  }

  function toggleCard(i) {
    document.getElementById('body-'   + i).classList.toggle('open');
    document.getElementById('toggle-' + i).classList.toggle('open');
  }
  function expandAll()  { results.forEach((_, i) => { document.getElementById('body-'+i)?.classList.add('open');    document.getElementById('toggle-'+i)?.classList.add('open');    }); }
  function collapseAll(){ results.forEach((_, i) => { document.getElementById('body-'+i)?.classList.remove('open'); document.getElementById('toggle-'+i)?.classList.remove('open'); }); }

  async function copyText(i, e) {
    e.stopPropagation();
    const btn = e.currentTarget;
    try {
      const res = await window.pywebview.api.copy_to_clipboard({ text: results[i].text });
      btn.textContent = res.ok ? '✓ Copied!' : '✗ Failed';
    } catch (_) {
      btn.textContent = '✗ Failed';
    }
    setTimeout(() => { btn.textContent = '⎘ Copy'; }, 1500);
  }

  async function exportTxt() {
    const name    = document.getElementById('outputFile').value || 'transcripts.txt';
    const content = results.map(r => r.name + '\\n' + r.text + '\\n').join('\\n');
    document.getElementById('exportBtn').disabled = true;
    log('Opening save dialog...', 'info');
    try {
      const res = await window.pywebview.api.save_file({ content, default_name: name });
      if (res.cancelled)  log('Export cancelled.', 'warn');
      else if (res.error) log('Export error: ' + res.error, 'error');
      else                log('Saved to: ' + res.path, 'success');
    } catch (e) {
      log('Export failed: ' + e.message, 'error');
    }
    document.getElementById('exportBtn').disabled = results.length === 0;
  }

  // ── Utilities ─────────────────────────────────────────────────────────────
  function log(msg, type) {
    type = type || 'info';
    const box  = document.getElementById('logBox');
    const ts   = new Date().toLocaleTimeString('en-US', { hour12: false });
    const line = document.createElement('span');
    line.className   = 'log-line ' + type;
    line.textContent = '[' + ts + '] ' + msg;
    box.appendChild(document.createElement('br'));
    box.appendChild(line);
    box.scrollTop = box.scrollHeight;
  }

  function clearLog() { document.getElementById('logBox').innerHTML = '<span class="log-line">Log cleared.</span>'; }

  function setStatus(s) {
    document.getElementById('statusDot').className    = 'dot ' + s;
    document.getElementById('statusText').textContent = s.toUpperCase();
  }

  function escHtml(s) {
    return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  }

  // ── Model download progress ───────────────────────────────────────────────
  function onModelDownloadStart(modelName) {
    document.getElementById('downloadBanner').classList.add('visible');
    document.getElementById('downloadTitle').textContent = 'Downloading model: ' + modelName;
    document.getElementById('downloadDesc').textContent  = 'This only happens once. Please wait...';
    document.getElementById('downloadFill').style.width  = '0%';
    document.getElementById('downloadPct').textContent   = '0%';
    log('Model "' + modelName + '" not found locally — downloading...', 'warn');
  }

  function onModelDownloadProgress(data) {
    document.getElementById('downloadFill').style.width = data.pct + '%';
    document.getElementById('downloadPct').textContent  = data.pct + '%';
    if (data.desc) document.getElementById('downloadDesc').textContent = data.desc;
  }

  function onModelDownloadDone() {
    document.getElementById('downloadBanner').classList.remove('visible');
    document.getElementById('downloadFill').style.width = '100%';
    log('Model downloaded and ready.', 'success');
  }
</script>
</body>
</html>"""


# ── Entry point ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    api = API()

    global _window
    window = webview.create_window(
        title="Transcribo",
        html=HTML,
        js_api=api,
        width=920,
        height=820,
        min_size=(720, 600),
        resizable=True,
        background_color="#0a0a0f",
    )
    _window = window

    def bind(w):
        """Bind DOM drag & drop events after window loads — official pywebview 6 pattern."""
        def on_drag(e):
            pass  # visual feedback handled in JS

        def on_drop(e):
            try:
                files = e['dataTransfer']['files']
            except (KeyError, TypeError):
                return
            audio = [
                f['pywebviewFullPath']
                for f in files
                if f.get('pywebviewFullPath') and
                   os.path.splitext(f['pywebviewFullPath'])[1].lower() in SUPPORTED
            ]
            if audio:
                w.evaluate_js('addFilePaths(' + json.dumps(audio) + ')')

        w.dom.document.events.dragenter += DOMEventHandler(on_drag, True, True)
        w.dom.document.events.dragstart += DOMEventHandler(on_drag, True, True)
        w.dom.document.events.dragover  += DOMEventHandler(on_drag, True, True, debounce=500)
        w.dom.document.events.drop      += DOMEventHandler(on_drop, True, True)

    _window_ref[0] = window
    webview.start(bind, window, debug=False)
