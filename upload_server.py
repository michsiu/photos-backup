import os
import zipfile
import io
import tempfile
import shutil
import threading
import time
from pathlib import Path
from flask import Flask, request, jsonify
import json

app = Flask(__name__)




BASE_DIR = Path(__file__).resolve().parent
INCOMING_DIR = BASE_DIR / "incoming"
INCOMING_DIR.mkdir(exist_ok=True)

ALLOWED_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.tiff'}
ZIP_EXTENSION = '.zip'

def log(msg):
    print(f"[UPLOAD] {msg}", flush=True)

def safe_filename(name):
    # 防止目录穿越
    return os.path.basename(name)

def save_file(file_storage):
    """保存单个文件到 incoming，返回保存的文件名"""
    fname = safe_filename(file_storage.filename)
    save_path = INCOMING_DIR / fname
    # 处理重名（简单加序号）
    counter = 1
    while save_path.exists():
        stem = os.path.splitext(fname)[0]
        ext = os.path.splitext(fname)[1]
        save_path = INCOMING_DIR / f"{stem}_{counter}{ext}"
        counter += 1
    file_storage.save(save_path)
    return save_path.name

def extract_zip(zip_path: Path):
    """解压 ZIP 到 incoming，返回解压出的文件数量"""
    extracted = []
    with zipfile.ZipFile(zip_path, 'r') as zf:
        for member in zf.infolist():
            # 跳过目录、隐藏文件和不可靠路径
            if member.is_dir():
                continue
            fname = os.path.basename(member.filename)
            if not fname or fname.startswith('.'):
                continue
            ext = os.path.splitext(fname)[1].lower()
            if ext not in ALLOWED_EXTENSIONS:
                continue
            # 解压到 incoming
            target_path = INCOMING_DIR / fname
            # 处理重名
            counter = 1
            while target_path.exists():
                stem = os.path.splitext(fname)[0]
                target_path = INCOMING_DIR / f"{stem}_{counter}{ext}"
                counter += 1
            with zf.open(member) as source, open(target_path, 'wb') as target:
                shutil.copyfileobj(source, target)
            extracted.append(target_path.name)
    # 删除原 zip
    zip_path.unlink()
    return len(extracted)


@app.route("/")
def index():
    return """

                <!doctype html>
<html lang="zh-CN">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Photo Upload</title>
    <style>
        :root {
            --bg: #f0f2f5;
            --card-bg: #ffffff;
            --text: #1a1a2e;
            --text-secondary: #6b7280;
            --text-muted: #9ca3af;
            --border: #e5e7eb;
            --border-hover: #818cf8;
            --primary: #6366f1;
            --primary-hover: #4f46e5;
            --primary-light: #eef2ff;
            --danger: #ef4444;
            --danger-hover: #dc2626;
            --log-bg: #0f172a;
            --log-text: #a7f3d0;
            --radius-sm: 8px;
            --radius: 14px;
            --radius-lg: 20px;
            --radius-xl: 28px;
            --shadow: 0 4px 20px rgba(0, 0, 0, 0.05), 0 1px 3px rgba(0, 0, 0, 0.04);
            --shadow-lg: 0 16px 40px rgba(0, 0, 0, 0.07), 0 4px 12px rgba(0, 0, 0, 0.04);
            --transition: 0.2s cubic-bezier(0.4, 0, 0.2, 1);
        }

        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", sans-serif;
            background: var(--bg);
            color: var(--text);
            padding: 28px 16px 40px;
            max-width: 680px;
            margin: 0 auto;
            min-height: 100vh;
            -webkit-font-smoothing: antialiased;
        }

        .header {
            display: flex;
            align-items: center;
            gap: 14px;
            margin-bottom: 28px;
        }
        .header .icon-wrap {
            width: 52px;
            height: 52px;
            border-radius: var(--radius);
            background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%);
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 1.8rem;
            box-shadow: 0 8px 24px rgba(99, 102, 241, 0.3);
            flex-shrink: 0;
        }
        .header h1 {
            font-size: 1.75rem;
            font-weight: 700;
            letter-spacing: -0.02em;
            color: #1e293b;
        }

        .card {
            background: var(--card-bg);
            border-radius: var(--radius-xl);
            padding: 28px 24px;
            box-shadow: var(--shadow);
            margin-bottom: 20px;
            border: 1px solid var(--border);
        }

        .upload-area {
            display: block;
            border: 2px solid #e2e8f0;
            border-radius: 16px;
            padding: 40px 20px;
            text-align: center;
            background: #ffffff;
            cursor: pointer;
            transition: all 0.2s;
            margin-bottom: 16px;
            user-select: none;
            -webkit-tap-highlight-color: transparent;
        }
        .upload-area:hover {
            border-color: #6366f1;
            background: #f8fafc;
        }
        .upload-area.drag-over {
            border-color: #6366f1 !important;
            background: #eef2ff !important;
            box-shadow: inset 0 0 0 4px rgba(99, 102, 241, 0.08);
        }
        .upload-area input {
            display: none;
        }
        .upload-icon {
            font-size: 2.8rem;
            margin-bottom: 8px;
            transition: transform var(--transition);
        }
        .upload-area:hover .upload-icon {
            transform: translateY(-3px);
        }
        .upload-area.drag-over .upload-icon {
            transform: translateY(-4px) scale(1.08);
        }
        .upload-text {
            font-size: 1.2rem;
            font-weight: 600;
            color: #334155;
        }
        .upload-hint {
            font-size: 0.9rem;
            color: #94a3b8;
            margin-top: 6px;
        }

        .file-list {
            margin-bottom: 16px;
            max-height: 150px;
            overflow-y: auto;
            scroll-behavior: smooth;
        }
        .file-list::-webkit-scrollbar {
            width: 5px;
        }
        .file-list::-webkit-scrollbar-track {
            background: transparent;
        }
        .file-list::-webkit-scrollbar-thumb {
            background: #d1d5db;
            border-radius: 10px;
        }
        .file-item {
            padding: 6px 12px;
            background: #f1f5f9;
            border-radius: 8px;
            margin-bottom: 4px;
            font-size: 0.9rem;
            color: #475569;
            word-break: break-all;
            animation: fadeIn 0.25s ease both;
        }
        @keyframes fadeIn {
            from {
                opacity: 0;
                transform: translateY(6px);
            }
            to {
                opacity: 1;
                transform: translateY(0);
            }
        }

        .btn-group {
            display: flex;
            gap: 12px;
            flex-wrap: wrap;
        }
        button {
            padding: 12px 24px;
            border: none;
            border-radius: 12px;
            font-weight: 600;
            cursor: pointer;
            font-size: 1rem;
            transition: all 0.2s;
            display: inline-flex;
            align-items: center;
            gap: 8px;
            outline: none;
            -webkit-tap-highlight-color: transparent;
        }
        button:active {
            transform: scale(0.96);
        }
        button:focus-visible {
            box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.35);
        }
        .btn-upload {
            background: #4f46e5;
            color: white;
        }
        .btn-upload:hover {
            background: #4338ca;
            transform: translateY(-1px);
            box-shadow: 0 6px 16px rgba(79, 70, 229, 0.3);
        }
        .btn-upload:disabled {
            background: #c7d2fe;
            cursor: not-allowed;
            transform: none;
            box-shadow: none;
            pointer-events: none;
        }
        .btn-stop {
            background: #ef4444;
            color: white;
        }
        .btn-stop:hover {
            background: #dc2626;
        }
        .btn-auto {
            background: #e2e8f0;
            color: #334155;
        }
        .btn-auto.active {
            background: #6366f1;
            color: white;
            animation: pulse-dot 2s infinite;
        }
        @keyframes pulse-dot {
            0%,
            100% {
                box-shadow: 0 0 0 0 rgba(99, 102, 241, 0.3);
            }
            50% {
                box-shadow: 0 0 0 8px rgba(99, 102, 241, 0);
            }
        }

        .progress-section {
            margin-top: 20px;
        }
        .progress-bar-bg {
            background: #e2e8f0;
            border-radius: 10px;
            height: 10px;
            overflow: hidden;
        }
        .progress-bar-fill {
            background: linear-gradient(90deg, #4f46e5, #6366f1);
            height: 100%;
            width: 0%;
            transition: width 0.3s;
            border-radius: 10px;
        }
        .stats {
            display: flex;
            justify-content: space-between;
            margin-top: 10px;
            font-size: 0.9rem;
            color: #64748b;
            flex-wrap: wrap;
            gap: 8px;
        }
        .stats span {
            display: flex;
            align-items: center;
            gap: 4px;
        }
        .stats .val {
            font-weight: 600;
            color: #334155;
        }

        #logBox {
            margin-top: 8px;
            background: #0f172a;
            color: #a7f3d0;
            padding: 16px;
            border-radius: 16px;
            height: 260px;
            overflow-y: auto;
            font-family: 'JetBrains Mono', Consolas, 'SF Mono', monospace;
            font-size: 0.8rem;
            line-height: 1.6;
            white-space: pre-wrap;
            word-break: break-all;
            scroll-behavior: smooth;
        }
        #logBox::-webkit-scrollbar {
            width: 5px;
        }
        #logBox::-webkit-scrollbar-track {
            background: transparent;
        }
        #logBox::-webkit-scrollbar-thumb {
            background: #334155;
            border-radius: 10px;
        }

        .footer {
            margin-top: 12px;
            font-size: 0.85rem;
            color: #94a3b8;
            text-align: center;
        }
        .footer strong {
            color: #6366f1;
            font-weight: 600;
        }

        .toast {
            position: fixed;
            top: 20px;
            left: 50%;
            transform: translateX(-50%) translateY(-120px);
            background: #1f2937;
            color: #fff;
            padding: 12px 22px;
            border-radius: 30px;
            font-weight: 600;
            font-size: 0.9rem;
            z-index: 999;
            pointer-events: none;
            transition: transform 0.35s cubic-bezier(0.22, 0.61, 0.36, 1);
            box-shadow: 0 12px 32px rgba(0, 0, 0, 0.2);
            white-space: nowrap;
        }
        .toast.show {
            transform: translateX(-50%) translateY(0);
        }
        .toast.success {
            background: #059669;
        }
        .toast.error {
            background: #dc2626;
        }

        @media (max-width: 520px) {
            body {
                padding: 16px 10px 32px;
            }
            .card {
                padding: 20px 16px;
                border-radius: var(--radius-lg);
            }
            .upload-area {
                padding: 30px 14px 26px;
            }
            .upload-text {
                font-size: 1rem;
            }
            .upload-icon {
                font-size: 2.2rem;
            }
            .header h1 {
                font-size: 1.4rem;
            }
            .header .icon-wrap {
                width: 40px;
                height: 40px;
                font-size: 1.4rem;
                border-radius: 12px;
            }
            button {
                padding: 10px 16px;
                font-size: 0.85rem;
                gap: 5px;
            }
            .btn-group {
                gap: 8px;
            }
            #logBox {
                height: 200px;
                font-size: 0.72rem;
                padding: 12px 14px;
            }
        }
    </style>
</head>
<body>

    <!-- Toast 提示 -->
    <div class="toast" id="toast"></div>

    <div class="header">
        <div class="icon-wrap">📷</div>
        <h1>Photo Upload</h1>
    </div>

    <div class="card">
        <!-- 上传区域 -->
        <label class="upload-area" id="uploadArea">
            <div class="upload-icon">⇧</div>
            <div class="upload-text">点击或拖拽文件到此处</div>
            <div class="upload-hint">支持 JPG, PNG, GIF, WEBP, ZIP</div>
            <input type="file" id="fileInput" multiple accept="image/*,.zip" />
        </label>

        <!-- 已选文件列表 -->
        <div class="file-list" id="fileList"></div>

        <div class="btn-group">
            <button class="btn-upload" id="btnUpload">⬆ 开始上传</button>
            <button class="btn-stop" id="btnStop">⏹ 停止服务</button>
            <button class="btn-auto" id="autoBtn">📋 自动日志</button>
        </div>

        <!-- 进度区域 -->
        <div class="progress-section" id="progressSection" style="display:none;">
            <div class="progress-bar-bg">
                <div class="progress-bar-fill" id="progressBar"></div>
            </div>
            <div class="stats">
                <span>📦 进度 <span class="val" id="taskCounter">0/0</span></span>
                <span>⚡ 速度 <span class="val" id="uploadSpeed">—</span></span>
            </div>
        </div>
    </div>

    <!-- 日志 -->
    <div class="card">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px;">
            <span style="font-weight:600;">📃 日志</span>
            <span style="font-size:0.8rem; color:#64748b;" id="logStatus">就绪</span>
        </div>
        <pre id="logBox"></pre>
    </div>

    <div class="footer">
        上传完成后点击 <strong>停止服务</strong>，系统将自动处理并提交到仓库。
    </div>

    <script>
        (function() {
            // ── 核心变量 ──
            let auto = false,
                timer = null;
            let totalFiles = 0,
                finishedFiles = 0;
            let startTime = 0;
            let isUploading = false;

            // ── DOM 引用 ──
            const progressSection = document.getElementById('progressSection');
            const progressBar = document.getElementById('progressBar');
            const taskCounter = document.getElementById('taskCounter');
            const uploadSpeed = document.getElementById('uploadSpeed');
            const logStatus = document.getElementById('logStatus');
            const fileInput = document.getElementById('fileInput');
            const fileList = document.getElementById('fileList');
            const btnUpload = document.getElementById('btnUpload');
            const btnStop = document.getElementById('btnStop');
            const autoBtn = document.getElementById('autoBtn');
            const uploadArea = document.getElementById('uploadArea');
            const logBox = document.getElementById('logBox');
            const toast = document.getElementById('toast');

            // ── Toast 提示 ──
            let toastTimer;

            function showToast(msg, type) {
                if (!toast) return;
                clearTimeout(toastTimer);
                toast.textContent = msg;
                toast.className = 'toast ' + (type || '') + ' show';
                toastTimer = setTimeout(function() {
                    toast.classList.remove('show');
                }, 2200);
            }

            // ── 日志函数 ──
            function log(msg) {
                if (!logBox) return;
                logBox.textContent += msg + '\n';
                logBox.scrollTop = logBox.scrollHeight;
            }

            // ── 清空并初始化日志 ──
            if (logBox) {
                logBox.textContent = '';
            }
            log('📋 就绪 — 请选择文件或拖拽到上方区域');

            // ── 更新进度 ──
            function updateProgress() {
                const pct = totalFiles > 0 ? Math.round((finishedFiles / totalFiles) * 100) : 0;
                if (progressBar) progressBar.style.width = pct + '%';
                if (taskCounter) taskCounter.innerText = finishedFiles + '/' + totalFiles;

                if (finishedFiles > 0 && startTime > 0) {
                    const elapsed = (Date.now() - startTime) / 1000;
                    const speed = elapsed > 0 ? (finishedFiles / elapsed).toFixed(2) : '—';
                    if (uploadSpeed) uploadSpeed.innerText = speed + ' 个/秒';
                } else {
                    if (uploadSpeed) uploadSpeed.innerText = '—';
                }

                if (logStatus) {
                    if (totalFiles > 0 && finishedFiles === totalFiles) {
                        logStatus.innerText = '全部上传完成 ✅';
                    } else if (totalFiles > 0 && finishedFiles > 0) {
                        logStatus.innerText = '上传中 ' + finishedFiles + '/' + totalFiles;
                    } else if (totalFiles > 0) {
                        logStatus.innerText = '待上传 ' + totalFiles + ' 个';
                    } else {
                        logStatus.innerText = '就绪';
                    }
                }
            }

            // ── 渲染文件列表 ──
            function renderFileList(files) {
                if (!fileList) return;
                fileList.innerHTML = '';
                if (!files || files.length === 0) {
                    log('未选择文件');
                    if (progressSection) progressSection.style.display = 'none';
                    totalFiles = 0;
                    finishedFiles = 0;
                    startTime = 0;
                    updateProgress();
                    return;
                }
                log('已选择 ' + files.length + ' 个文件:');
                for (let i = 0; i < files.length; i++) {
                    const f = files[i];
                    log('  · ' + f.name);
                    const item = document.createElement('div');
                    item.className = 'file-item';
                    item.textContent = f.name;
                    fileList.appendChild(item);
                }
                // 显示进度区域并重置
                if (progressSection) progressSection.style.display = 'block';
                totalFiles = files.length;
                finishedFiles = 0;
                startTime = 0;
                updateProgress();
            }

            // ── 监听文件选择 ──
            fileInput.addEventListener('change', function() {
                const files = fileInput.files;
                renderFileList(files);
            });

            // ── 拖拽支持 ──
            uploadArea.addEventListener('dragover', function(e) {
                e.preventDefault();
                uploadArea.classList.add('drag-over');
            });
            uploadArea.addEventListener('dragleave', function(e) {
                e.preventDefault();
                uploadArea.classList.remove('drag-over');
            });
            uploadArea.addEventListener('drop', function(e) {
                e.preventDefault();
                uploadArea.classList.remove('drag-over');
                const files = e.dataTransfer.files;
                if (files.length > 0) {
                    // 通过 DataTransfer 设置文件并手动触发 change 事件
                    const dt = new DataTransfer();
                    for (let i = 0; i < files.length; i++) {
                        dt.items.add(files[i]);
                    }
                    fileInput.files = dt.files;
                    // 手动触发 change 事件，确保监听器执行
                    fileInput.dispatchEvent(new Event('change', { bubbles: true }));
                }
            });

            // ── 开始上传 ──
            async function startUpload() {
                if (isUploading) {
                    showToast('上传已在进行中', '');
                    return;
                }
                const files = fileInput.files;
                if (!files || files.length === 0) {
                    log('⚠ 请先选择文件');
                    showToast('请先选择文件', 'error');
                    return;
                }

                isUploading = true;
                if (btnUpload) {
                    btnUpload.disabled = true;
                    btnUpload.textContent = '⏳ 上传中...';
                }
                totalFiles = files.length;
                finishedFiles = 0;
                startTime = Date.now();
                if (progressSection) progressSection.style.display = 'block';
                updateProgress();
                log('🚀 开始上传 ' + totalFiles + ' 个文件...');

                const tasks = Array.from(files).map(async function(f) {
                    const fd = new FormData();
                    fd.append('image', f);
                    try {
                        const resp = await fetch('/upload', { method: 'POST', body: fd });
                        const json = await resp.json();
                        if (json.ok) {
                            finishedFiles++;
                            updateProgress();
                            log('✔ ' + f.name);
                        } else {
                            finishedFiles++;
                            updateProgress();
                            log('❌ ' + f.name + ' 失败: ' + (json.error || '未知错误'));
                        }
                    } catch (e) {
                        finishedFiles++;
                        updateProgress();
                        log('❌ ' + f.name + ' 网络错误: ' + (e.message || e));
                    }
                });

                await Promise.all(tasks);
                isUploading = false;
                if (btnUpload) {
                    btnUpload.disabled = false;
                    btnUpload.textContent = '⬆ 开始上传';
                }
                log('✅ 批次上传结束');
                if (finishedFiles === totalFiles) {
                    log('🎉 所有文件上传成功，可以点击"停止服务"');
                    showToast('全部上传完成 🎉', 'success');
                } else {
                    showToast(finishedFiles + '/' + totalFiles + ' 完成', '');
                }
            }

            // ── 停止服务 ──
            async function shutdownServer() {
                log('🛑 正在停止服务...');
                if (btnStop) {
                    btnStop.textContent = '⏳ 停止中...';
                    btnStop.style.pointerEvents = 'none';
                    btnStop.style.opacity = '0.7';
                }
                try {
                    const resp = await fetch('/shutdown', { method: 'POST' });
                    const json = await resp.json();
                    log('✔ 服务已停止: ' + JSON.stringify(json));
                    if (logStatus) logStatus.innerText = '服务已停止 – 正在处理照片';
                    showToast('服务已停止', 'success');
                } catch (e) {
                    log('❌ 停止失败: ' + (e.message || e));
                    showToast('停止失败', 'error');
                } finally {
                    if (btnStop) {
                        btnStop.textContent = '⏹ 停止服务';
                        btnStop.style.pointerEvents = 'auto';
                        btnStop.style.opacity = '1';
                    }
                }
                isUploading = false;
                if (btnUpload) {
                    btnUpload.disabled = false;
                    btnUpload.textContent = '⬆ 开始上传';
                }
            }

            // ── 自动日志 ──
            function toggleAuto() {
                auto = !auto;
                if (auto) {
                    if (autoBtn) {
                        autoBtn.classList.add('active');
                        autoBtn.innerHTML = '📋 自动日志 (开)';
                    }
                    log('[AUTO] 开始轮询日志...');
                    timer = setInterval(async function() {
                        try {
                            const r = await fetch('/logs');
                            const j = await r.json();
                            log('[AUTO] ' + JSON.stringify(j));
                        } catch (e) {
                            log('[AUTO ERR] ' + (e.message || e));
                        }
                    }, 3000);
                    showToast('自动日志已开启');
                } else {
                    if (autoBtn) {
                        autoBtn.classList.remove('active');
                        autoBtn.innerHTML = '📋 自动日志';
                    }
                    clearInterval(timer);
                    timer = null;
                    log('[AUTO] 停止轮询');
                    showToast('自动日志已关闭');
                }
            }

            // ── 页面卸载清理 ──
            window.addEventListener('beforeunload', function() {
                if (timer) clearInterval(timer);
            });

            // ── 暴露到全局作用域，供 onclick 调用 ──
            window.startUpload = startUpload;
            window.shutdownServer = shutdownServer;
            window.toggleAuto = toggleAuto;

            // ── 按钮事件绑定（双重保障） ──
            if (btnUpload) {
                btnUpload.addEventListener('click', function(e) {
                    // 如果 onclick 未触发，这里作为后备
                    // 但为了避免重复执行，这里不额外调用，仅保留 onclick
                });
                // 同时绑定原生事件以防 onclick 失效
                btnUpload.onclick = function(e) {
                    e.preventDefault();
                    startUpload();
                };
            }
            if (btnStop) {
                btnStop.onclick = function(e) {
                    e.preventDefault();
                    shutdownServer();
                };
            }
            if (autoBtn) {
                autoBtn.onclick = function(e) {
                    e.preventDefault();
                    toggleAuto();
                };
            }

            // ── 初始化完成 ──
            log('✅ 页面就绪，等待操作...');
        })();
    </script>
</body>
</html>
                
                
                """

@app.route("/upload", methods=["POST"])
def upload():
    try:
        file = request.files.get("image")
        if not file or file.filename == '':
            return jsonify({"ok": False, "error": "无文件"}), 400

        ext = os.path.splitext(file.filename)[1].lower()
        if ext == ZIP_EXTENSION:
            # 保存 ZIP 并解压
            zip_path = INCOMING_DIR / safe_filename(file.filename)
            file.save(zip_path)
            count = extract_zip(zip_path)
            log(f"ZIP 解压完成，释放 {count} 张图片")
            return jsonify({"ok": True, "zip": True, "extracted": count})
        elif ext in ALLOWED_EXTENSIONS:
            saved_name = save_file(file)
            log(f"图片已保存: {saved_name}")
            return jsonify({"ok": True, "name": saved_name})
        else:
            return jsonify({"ok": False, "error": f"不支持的文件类型 {ext}"}), 400
    except Exception as e:
        log(f"上传错误: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500

@app.route("/logs")
def logs():
    return jsonify({"status": "uploading", "time": __import__('datetime').datetime.utcnow().isoformat()})

@app.route("/shutdown", methods=["POST"])
def shutdown():
    log("收到关闭信号")
    def killer():
        time.sleep(0.5)
        os._exit(0)
    threading.Thread(target=killer).start()
    return jsonify({"ok": True, "message": "服务关闭中"})


    
    





@app.route('/gallery')
def gallery():
    try:
        with open("photos.json", 'r', encoding='utf-8') as f:
            photos = json.load(f)
    except Exception:
        photos = {}

    # 动态构建 raw_base
    repo = os.environ.get("GITHUB_REPOSITORY", "user/repo")
    branch = os.environ.get("GITHUB_REF", "refs/heads/main").replace("refs/heads/", "")
    user, repo_name = repo.split("/")
    raw_base = f"https://raw.githubusercontent.com/{user}/{repo_name}/{branch}/"

    photos_json = json.dumps(photos, ensure_ascii=False)

    return f"""
<!doctype html>
<html lang="zh-CN">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Photo Gallery</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #f4f6f9; color: #1e293b; }}
        .container {{ max-width: 1400px; margin: 0 auto; padding: 20px; }}
        h1 {{ text-align: center; margin-bottom: 20px; }}
        .controls {{ display: flex; flex-wrap: wrap; gap: 12px; margin-bottom: 20px; }}
        .controls input, .controls select {{ padding: 10px 12px; border: 1px solid #cbd5e1; border-radius: 8px; }}
        .controls input {{ flex: 1; min-width: 200px; }}
        .grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 14px; }}
        .card {{ background: #fff; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 12px rgba(0,0,0,0.06); }}
        .card img {{ width: 100%; height: 220px; object-fit: cover; display: block; }}
        .card-info {{ padding: 10px; }}
        .name {{ font-size: 14px; font-weight: 600; overflow: hidden; white-space: nowrap; text-overflow: ellipsis; }}
        .date {{ font-size: 12px; color: #64748b; margin-top: 4px; }}
        .loading {{ text-align: center; padding: 20px; color: #64748b; }}
        #sentinel {{ height: 1px; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>📷 Photo Gallery</h1>
        <div class="controls">
            <input id="search" placeholder="搜索文件名">
            <select id="yearFilter"><option value="">所有年份</option></select>
            <select id="sortBy">
                <option value="date-desc">时间 ↓</option>
                <option value="date-asc">时间 ↑</option>
                <option value="name-asc">名称 A-Z</option>
                <option value="name-desc">名称 Z-A</option>
                <option value="random">随机</option>
            </select>
        </div>
        <div class="grid" id="grid"></div>
        <div class="loading" id="loading">加载中...</div>
        <div id="sentinel"></div>
    </div>
    <script>
        var RAW_BASE = "{raw_base}";
        var ALL_PHOTOS_DATA = {photos_json};
        var PER_LOAD = 20;
        var allPhotos = [];
        var filteredPhotos = [];
        var renderedCount = 0;
        var loading = false;
        var grid = document.getElementById("grid");
        var loadingEl = document.getElementById("loading");

        function initPhotos() {{
            var raw = ALL_PHOTOS_DATA;
            allPhotos = Object.keys(raw).map(function(sha) {{
                var item = raw[sha];
                item.sha256 = sha;
                return item;
            }});
            initYearFilter();
            bindEvents();
            applyFilters();
        }}

        function initYearFilter() {{
            var years = [];
            allPhotos.forEach(function(p) {{
                if (p.year && years.indexOf(p.year) === -1) years.push(p.year);
            }});
            years.sort().reverse();
            var select = document.getElementById("yearFilter");
            years.forEach(function(y) {{
                var opt = document.createElement("option");
                opt.value = y;
                opt.textContent = y;
                select.appendChild(opt);
            }});
        }}

        function bindEvents() {{
            document.getElementById("search").addEventListener("input", debounce(applyFilters, 200));
            document.getElementById("yearFilter").addEventListener("change", applyFilters);
            document.getElementById("sortBy").addEventListener("change", applyFilters);
        }}

        function applyFilters() {{
            var search = document.getElementById("search").value.toLowerCase();
            var year = document.getElementById("yearFilter").value;
            var sort = document.getElementById("sortBy").value;
            filteredPhotos = allPhotos.filter(function(p) {{
                var matchName = !search || p.fileName.toLowerCase().indexOf(search) !== -1;
                var matchYear = !year || p.year == year;
                return matchName && matchYear;
            }});
            if (sort === "date-asc") filteredPhotos.sort(function(a,b) {{ return new Date(a.date) - new Date(b.date); }});
            if (sort === "date-desc") filteredPhotos.sort(function(a,b) {{ return new Date(b.date) - new Date(a.date); }});
            if (sort === "name-asc") filteredPhotos.sort(function(a,b) {{ return a.fileName.localeCompare(b.fileName); }});
            if (sort === "name-desc") filteredPhotos.sort(function(a,b) {{ return b.fileName.localeCompare(a.fileName); }});
            if (sort === "random") shuffle(filteredPhotos);
            renderedCount = 0;
            grid.innerHTML = "";
            loadMore();
        }}

        function loadMore() {{
            if (loading) return;
            loading = true;
            var slice = filteredPhotos.slice(renderedCount, renderedCount + PER_LOAD);
            if (slice.length === 0) {{ loadingEl.innerHTML = "已经到底了"; loading = false; return; }}
            var frag = document.createDocumentFragment();
            slice.forEach(function(p) {{ frag.appendChild(createCard(p)); }});
            grid.appendChild(frag);
            renderedCount += slice.length;
            loadingEl.innerHTML = renderedCount >= filteredPhotos.length ? "已经到底了" : "已加载 " + renderedCount + " / " + filteredPhotos.length;
            loading = false;
        }}

        function createCard(photo) {{
            var card = document.createElement("div");
            card.className = "card";
            var imgUrl = RAW_BASE + "/" + photo.url;
            var thumbUrl = RAW_BASE + "/" + photo.thumbnail;
            card.innerHTML = '<a href="' + imgUrl + '" target="_blank"><img src="' + thumbUrl + '" loading="lazy" alt="' + photo.fileName + '"></a><div class="card-info"><div class="name">' + photo.fileName + '</div><div class="date">' + (photo.date || "") + '</div></div>';
            return card;
        }}

        function shuffle(arr) {{ for (var i = arr.length - 1; i > 0; i--) {{ var j = Math.floor(Math.random() * (i + 1)); var tmp = arr[i]; arr[i] = arr[j]; arr[j] = tmp; }} }}

        function debounce(fn, delay) {{ var timer; return function() {{ clearTimeout(timer); var args = arguments; var self = this; timer = setTimeout(function() {{ fn.apply(self, args); }}, delay); }}; }}

        var observer = new IntersectionObserver(function(entries) {{ if (entries[0].isIntersecting && renderedCount < filteredPhotos.length) loadMore(); }}, {{ rootMargin: "1000px" }});
        observer.observe(document.getElementById("sentinel"));
        initPhotos();
    </script>
</body>
</html>
"""








if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)


    
