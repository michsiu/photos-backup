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
    return """<!doctype html>
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
            --primary-shadow: rgba(99, 102, 241, 0.25);
            --danger: #ef4444;
            --danger-hover: #dc2626;
            --success: #10b981;
            --warning: #f59e0b;
            --log-bg: #0f172a;
            --log-text: #a7f3d0;
            --log-dim: #64748b;
            --radius-sm: 8px;
            --radius: 14px;
            --radius-lg: 20px;
            --radius-xl: 28px;
            --shadow-xs: 0 1px 2px rgba(0, 0, 0, 0.04);
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
            -moz-osx-font-smoothing: grayscale;
        }

        /* ── Header ────────────────────── */
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

        /* ── Card ──────────────────────── */
        .card {
            background: var(--card-bg);
            border-radius: var(--radius-xl);
            padding: 28px 24px;
            box-shadow: var(--shadow);
            margin-bottom: 20px;
            border: 1px solid var(--border);
            transition: box-shadow var(--transition);
        }
        .card:hover {
            box-shadow: var(--shadow-lg);
        }
        .card-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 14px;
            flex-wrap: wrap;
            gap: 8px;
        }
        .card-header .label {
            font-weight: 700;
            font-size: 0.95rem;
            display: flex;
            align-items: center;
            gap: 8px;
            color: #374151;
        }
        .card-header .badge {
            font-size: 0.75rem;
            font-weight: 600;
            padding: 4px 10px;
            border-radius: 20px;
            background: #f3f4f6;
            color: #6b7280;
            transition: all var(--transition);
            white-space: nowrap;
        }
        .badge.success {
            background: #ecfdf5;
            color: #059669;
        }
        .badge.warning {
            background: #fffbeb;
            color: #d97706;
        }
        .badge.info {
            background: #eef2ff;
            color: #4f46e5;
        }

        /* ── Upload Area ───────────────── */
        .upload-area {
            display: block;
            border: 2px dashed var(--border);
            border-radius: var(--radius-lg);
            padding: 44px 20px 38px;
            text-align: center;
            background: #fafbfc;
            cursor: pointer;
            transition: all var(--transition);
            position: relative;
            overflow: hidden;
            user-select: none;
            -webkit-tap-highlight-color: transparent;
        }
        .upload-area::before {
            content: '';
            position: absolute;
            inset: 0;
            background: radial-gradient(circle at 50% 30%, rgba(99, 102, 241, 0.04) 0%, transparent 70%);
            opacity: 0;
            transition: opacity var(--transition);
            pointer-events: none;
        }
        .upload-area:hover {
            border-color: var(--border-hover);
            background: #f8f9fd;
            box-shadow: inset 0 0 0 4px rgba(99, 102, 241, 0.03);
        }
        .upload-area:hover::before {
            opacity: 1;
        }
        .upload-area.drag-over {
            border-color: var(--primary) !important;
            background: #eef2ff !important;
            box-shadow: inset 0 0 0 6px rgba(99, 102, 241, 0.06) !important;
            transform: scale(1.01);
        }
        .upload-area.drag-over::before {
            opacity: 1;
        }
        .upload-area input {
            display: none;
        }
        .upload-icon-svg {
            width: 56px;
            height: 56px;
            margin: 0 auto 12px;
            background: var(--primary-light);
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 1.8rem;
            transition: transform var(--transition), box-shadow var(--transition);
        }
        .upload-area:hover .upload-icon-svg {
            transform: translateY(-3px);
            box-shadow: 0 8px 20px rgba(99, 102, 241, 0.2);
        }
        .upload-area.drag-over .upload-icon-svg {
            transform: translateY(-4px) scale(1.08);
            box-shadow: 0 12px 28px rgba(99, 102, 241, 0.3);
        }
        .upload-text {
            font-size: 1.15rem;
            font-weight: 650;
            color: #374151;
            letter-spacing: -0.01em;
        }
        .upload-hint {
            font-size: 0.85rem;
            color: var(--text-muted);
            margin-top: 5px;
            transition: color var(--transition);
        }
        .upload-area:hover .upload-hint {
            color: var(--primary);
        }

        /* ── File List ─────────────────── */
        .file-list-wrap {
            margin-top: 14px;
            max-height: 180px;
            overflow-y: auto;
            scroll-behavior: smooth;
            padding-right: 2px;
        }
        .file-list-wrap::-webkit-scrollbar {
            width: 5px;
        }
        .file-list-wrap::-webkit-scrollbar-track {
            background: transparent;
        }
        .file-list-wrap::-webkit-scrollbar-thumb {
            background: #d1d5db;
            border-radius: 10px;
        }
        .file-item {
            display: flex;
            align-items: center;
            gap: 10px;
            padding: 10px 14px;
            background: #f9fafb;
            border-radius: var(--radius-sm);
            margin-bottom: 5px;
            font-size: 0.88rem;
            color: #374151;
            border: 1px solid transparent;
            transition: all var(--transition);
            animation: fadeInUp 0.25s ease both;
        }
        @keyframes fadeInUp {
            from {
                opacity: 0;
                transform: translateY(8px);
            }
            to {
                opacity: 1;
                transform: translateY(0);
            }
        }
        .file-item:hover {
            background: #f3f4f6;
            border-color: #e5e7eb;
        }
        .file-item .thumb {
            width: 36px;
            height: 36px;
            border-radius: 6px;
            object-fit: cover;
            flex-shrink: 0;
            background: #e5e7eb;
            font-size: 0.7rem;
            display: flex;
            align-items: center;
            justify-content: center;
            color: #9ca3af;
            overflow: hidden;
        }
        .file-item .info {
            flex: 1;
            min-width: 0;
        }
        .file-item .info .name {
            font-weight: 500;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
            color: #1f2937;
        }
        .file-item .info .size {
            font-size: 0.75rem;
            color: #9ca3af;
            margin-top: 1px;
        }
        .file-item .btn-remove {
            width: 28px;
            height: 28px;
            border-radius: 50%;
            border: none;
            background: transparent;
            cursor: pointer;
            font-size: 1rem;
            color: #9ca3af;
            display: flex;
            align-items: center;
            justify-content: center;
            flex-shrink: 0;
            transition: all var(--transition);
            padding: 0;
            line-height: 1;
        }
        .file-item .btn-remove:hover {
            background: #fee2e2;
            color: #ef4444;
        }
        .file-list-empty {
            text-align: center;
            padding: 18px 0 6px;
            color: #c5c9d2;
            font-size: 0.9rem;
            user-select: none;
        }

        /* ── Buttons ───────────────────── */
        .btn-group {
            display: flex;
            gap: 10px;
            flex-wrap: wrap;
            margin-top: 18px;
        }
        button {
            padding: 11px 20px;
            border: none;
            border-radius: var(--radius);
            font-weight: 600;
            cursor: pointer;
            font-size: 0.92rem;
            transition: all var(--transition);
            display: inline-flex;
            align-items: center;
            gap: 7px;
            letter-spacing: -0.01em;
            white-space: nowrap;
            position: relative;
            overflow: hidden;
            -webkit-tap-highlight-color: transparent;
            outline: none;
        }
        button:active {
            transform: scale(0.96);
        }
        button:focus-visible {
            box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.35);
        }
        .btn-upload {
            background: var(--primary);
            color: #fff;
            box-shadow: 0 4px 14px var(--primary-shadow);
        }
        .btn-upload:hover {
            background: var(--primary-hover);
            box-shadow: 0 8px 22px rgba(99, 102, 241, 0.35);
            transform: translateY(-1px);
        }
        .btn-upload:disabled {
            background: #c7d2fe;
            cursor: not-allowed;
            box-shadow: none;
            transform: none;
            pointer-events: none;
        }
        .btn-stop {
            background: #fff;
            color: var(--danger);
            border: 1.5px solid #fecaca;
        }
        .btn-stop:hover {
            background: #fef2f2;
            border-color: #f87171;
            transform: translateY(-1px);
        }
        .btn-auto {
            background: #f3f4f6;
            color: #4b5563;
            border: 1.5px solid transparent;
        }
        .btn-auto:hover {
            background: #e5e7eb;
        }
        .btn-auto.active {
            background: #eef2ff;
            color: #4f46e5;
            border-color: #c7d2fe;
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
        .btn-clear {
            background: transparent;
            color: #9ca3af;
            padding: 8px 14px;
            font-size: 0.82rem;
            font-weight: 500;
            border: 1px solid transparent;
        }
        .btn-clear:hover {
            color: #6b7280;
            background: #f3f4f6;
            border-color: #e5e7eb;
        }

        /* ── Progress ──────────────────── */
        .progress-section {
            margin-top: 18px;
            animation: fadeInUp 0.3s ease both;
        }
        .progress-bar-wrap {
            background: #e5e7eb;
            border-radius: 20px;
            height: 12px;
            overflow: hidden;
            position: relative;
        }
        .progress-bar-fill {
            background: linear-gradient(90deg, #6366f1 0%, #8b5cf6 100%);
            height: 100%;
            width: 0%;
            border-radius: 20px;
            transition: width 0.4s cubic-bezier(0.22, 0.61, 0.36, 1);
            position: relative;
        }
        .progress-bar-fill::after {
            content: '';
            position: absolute;
            right: 2px;
            top: 2px;
            bottom: 2px;
            width: 8px;
            border-radius: 50%;
            background: rgba(255, 255, 255, 0.7);
        }
        .stats {
            display: flex;
            justify-content: space-between;
            margin-top: 10px;
            font-size: 0.82rem;
            color: #6b7280;
            flex-wrap: wrap;
            gap: 6px;
        }
        .stats span {
            display: flex;
            align-items: center;
            gap: 4px;
        }
        .stats .val {
            font-weight: 600;
            color: #374151;
        }

        /* ── Log ───────────────────────── */
        #logBox {
            margin-top: 8px;
            background: var(--log-bg);
            color: var(--log-text);
            padding: 16px 18px;
            border-radius: var(--radius);
            height: 250px;
            overflow-y: auto;
            font-family: 'SF Mono', 'JetBrains Mono', 'Fira Code', Consolas, monospace;
            font-size: 0.78rem;
            line-height: 1.7;
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
        #logBox .log-error {
            color: #fca5a5;
        }
        #logBox .log-success {
            color: #6ee7b7;
        }
        #logBox .log-warn {
            color: #fde68a;
        }
        #logBox .log-info {
            color: #93c5fd;
        }

        /* ── Footer ────────────────────── */
        .footer {
            margin-top: 8px;
            font-size: 0.82rem;
            color: #9ca3af;
            text-align: center;
            line-height: 1.6;
        }
        .footer strong {
            color: #6366f1;
            font-weight: 600;
        }

        /* ── Toast ─────────────────────── */
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

        /* ── Responsive ────────────────── */
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
            .upload-icon-svg {
                width: 44px;
                height: 44px;
                font-size: 1.4rem;
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

    <!-- Toast -->
    <div class="toast" id="toast"></div>

    <!-- Header -->
    <div class="header">
        <div class="icon-wrap">📷</div>
        <h1>Photo Upload</h1>
    </div>

    <!-- 上传卡片 -->
    <div class="card">
        <label class="upload-area" id="uploadArea" title="点击选择文件，或拖拽文件到此处">
            <div class="upload-icon-svg">⬆️</div>
            <div class="upload-text">点击或拖拽文件到此处</div>
            <div class="upload-hint">支持 JPG · PNG · GIF · WEBP · ZIP</div>
            <input type="file" id="fileInput" multiple accept="image/*,.zip" />
        </label>

        <!-- 文件列表 -->
        <div class="file-list-wrap" id="fileListWrap">
            <div class="file-list-empty" id="fileListEmpty">尚未选择文件</div>
            <div id="fileList"></div>
        </div>

        <!-- 操作按钮 -->
        <div class="btn-group">
            <button class="btn-upload" id="btnUpload" onclick="startUpload()">⬆ 开始上传</button>
            <button class="btn-stop" id="btnStop" onclick="shutdownServer()">⏹ 停止服务</button>
            <button class="btn-auto" id="autoBtn" onclick="toggleAuto()">📋 自动日志</button>
            <button class="btn-clear" id="btnClear" onclick="clearFiles()" style="display:none;">✕ 清空列表</button>
        </div>

        <!-- 进度条 -->
        <div class="progress-section" id="progressSection" style="display:none;">
            <div class="progress-bar-wrap">
                <div class="progress-bar-fill" id="progressBar"></div>
            </div>
            <div class="stats">
                <span>📦 进度 <span class="val" id="taskCounter">0/0</span></span>
                <span>⚡ 速度 <span class="val" id="uploadSpeed">—</span></span>
                <span>⏱ 耗时 <span class="val" id="elapsedTime">—</span></span>
            </div>
        </div>
    </div>

    <!-- 日志卡片 -->
    <div class="card">
        <div class="card-header">
            <span class="label">📃 日志</span>
            <span class="badge" id="logStatus">就绪</span>
        </div>
        <pre id="logBox"></pre>
    </div>

    <div class="footer">
        上传完成后点击 <strong>停止服务</strong>，系统将自动处理并提交到仓库。
    </div>

    <script>
        (function() {
            // ── 状态 ──────────────────────────
            let auto = false,
                timer = null;
            let totalFiles = 0,
                finishedFiles = 0;
            let startTime = 0;
            let isUploading = false;
            let selectedFiles = []; // 维护一份文件数组，便于删除

            // ── DOM 引用 ──────────────────────
            const progressSection = document.getElementById('progressSection');
            const progressBar = document.getElementById('progressBar');
            const taskCounter = document.getElementById('taskCounter');
            const uploadSpeed = document.getElementById('uploadSpeed');
            const elapsedTimeEl = document.getElementById('elapsedTime');
            const logStatus = document.getElementById('logStatus');
            const fileInput = document.getElementById('fileInput');
            const fileList = document.getElementById('fileList');
            const fileListEmpty = document.getElementById('fileListEmpty');
            const fileListWrap = document.getElementById('fileListWrap');
            const uploadArea = document.getElementById('uploadArea');
            const btnUpload = document.getElementById('btnUpload');
            const btnStop = document.getElementById('btnStop');
            const btnClear = document.getElementById('btnClear');
            const autoBtn = document.getElementById('autoBtn');
            const logBox = document.getElementById('logBox');
            const toast = document.getElementById('toast');

            // ── Toast ─────────────────────────
            let toastTimer;

            function showToast(msg, type = '') {
                clearTimeout(toastTimer);
                toast.textContent = msg;
                toast.className = 'toast ' + type + ' show';
                toastTimer = setTimeout(() => {
                    toast.classList.remove('show');
                }, 2200);
            }

            // ── 日志 ──────────────────────────
            function log(msg, cls = '') {
                const prefix = cls ? '' : '';
                logBox.textContent += (logBox.textContent ? '\n' : '') + msg;
                logBox.scrollTop = logBox.scrollHeight;
            }

            function logStyled(msg, type) {
                // type: 'success' | 'error' | 'warn' | 'info'
                const clsMap = {
                    success: 'log-success',
                    error: 'log-error',
                    warn: 'log-warn',
                    info: 'log-info'
                };
                log(msg, clsMap[type] || '');
            }

            // 初始日志
            log('📋 就绪 — 请选择文件或拖拽到上方区域');

            // ── 格式化文件大小 ────────────────
            function formatSize(bytes) {
                if (bytes === 0) return '0 B';
                const k = 1024;
                const sizes = ['B', 'KB', 'MB', 'GB'];
                const i = Math.floor(Math.log(bytes) / Math.log(k));
                return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
            }

            // ── 渲染文件列表 ──────────────────
            function renderFileList() {
                fileList.innerHTML = '';
                if (selectedFiles.length === 0) {
                    fileListEmpty.style.display = 'block';
                    btnClear.style.display = 'none';
                    fileListWrap.style.maxHeight = '60px';
                } else {
                    fileListEmpty.style.display = 'none';
                    btnClear.style.display = 'inline-flex';
                    fileListWrap.style.maxHeight = '180px';
                    selectedFiles.forEach((f, index) => {
                        const item = document.createElement('div');
                        item.className = 'file-item';
                        item.style.animationDelay = (index * 0.03) + 's';

                        // 缩略图（图片类型尝试生成预览）
                        const thumb = document.createElement('div');
                        thumb.className = 'thumb';
                        if (f.type.startsWith('image/')) {
                            const img = document.createElement('img');
                            img.src = URL.createObjectURL(f);
                            img.alt = '';
                            img.style.width = '100%';
                            img.style.height = '100%';
                            img.style.objectFit = 'cover';
                            img.onload = () => URL.revokeObjectURL(img.src);
                            thumb.appendChild(img);
                        } else {
                            thumb.textContent = '📄';
                        }

                        // 信息
                        const info = document.createElement('div');
                        info.className = 'info';
                        const nameEl = document.createElement('div');
                        nameEl.className = 'name';
                        nameEl.textContent = f.name;
                        const sizeEl = document.createElement('div');
                        sizeEl.className = 'size';
                        sizeEl.textContent = formatSize(f.size);
                        info.appendChild(nameEl);
                        info.appendChild(sizeEl);

                        // 删除按钮
                        const removeBtn = document.createElement('button');
                        removeBtn.className = 'btn-remove';
                        removeBtn.innerHTML = '×';
                        removeBtn.title = '移除文件';
                        removeBtn.addEventListener('click', (e) => {
                            e.stopPropagation();
                            e.preventDefault();
                            removeFile(index);
                        });

                        item.appendChild(thumb);
                        item.appendChild(info);
                        item.appendChild(removeBtn);
                        fileList.appendChild(item);
                    });
                }
            }

            function removeFile(index) {
                selectedFiles.splice(index, 1);
                syncFileInput();
                renderFileList();
                log(`🗑 已移除文件 (剩余 ${selectedFiles.length} 个)`);
                if (selectedFiles.length === 0) {
                    progressSection.style.display = 'none';
                }
            }

            function syncFileInput() {
                // 用 DataTransfer 更新 fileInput.files
                const dt = new DataTransfer();
                selectedFiles.forEach(f => dt.items.add(f));
                fileInput.files = dt.files;
            }

            function clearFiles() {
                if (isUploading) {
                    showToast('上传中，无法清空', 'error');
                    return;
                }
                selectedFiles = [];
                syncFileInput();
                renderFileList();
                progressSection.style.display = 'none';
                totalFiles = 0;
                finishedFiles = 0;
                startTime = 0;
                updateProgress();
                log('🗑 已清空全部文件');
                showToast('列表已清空');
            }

            // ── 文件选择处理 ──────────────────
            function handleFiles(files) {
                if (isUploading) {
                    showToast('上传中，请等待完成', 'error');
                    return;
                }
                const newFiles = Array.from(files);
                if (newFiles.length === 0) return;

                // 去重（按 name + size + lastModified）
                const existingKeys = new Set(
                    selectedFiles.map(f => f.name + '|' + f.size + '|' + f.lastModified)
                );
                const uniqueNew = newFiles.filter(
                    f => !existingKeys.has(f.name + '|' + f.size + '|' + f.lastModified)
                );

                if (uniqueNew.length < newFiles.length) {
                    showToast(`已跳过 ${newFiles.length - uniqueNew.length} 个重复文件`, '');
                }

                selectedFiles = [...selectedFiles, ...uniqueNew];
                syncFileInput();
                renderFileList();
                log(`📁 已选择 ${selectedFiles.length} 个文件 (本次新增 ${uniqueNew.length} 个)`);
                uniqueNew.forEach(f => {
                    log(`   · ${f.name}  (${formatSize(f.size)})`);
                });

                // 重置进度
                totalFiles = selectedFiles.length;
                finishedFiles = 0;
                startTime = 0;
                updateProgress();
                if (selectedFiles.length > 0 && progressSection.style.display === 'block') {
                    // keep progress visible but reset
                }
            }

            fileInput.addEventListener('change', () => {
                handleFiles(fileInput.files);
            });

            // ── 拖拽支持 ──────────────────────
            let dragCounter = 0;
            uploadArea.addEventListener('dragenter', (e) => {
                e.preventDefault();
                dragCounter++;
                uploadArea.classList.add('drag-over');
            });
            uploadArea.addEventListener('dragleave', (e) => {
                e.preventDefault();
                dragCounter--;
                if (dragCounter <= 0) {
                    dragCounter = 0;
                    uploadArea.classList.remove('drag-over');
                }
            });
            uploadArea.addEventListener('dragover', (e) => {
                e.preventDefault();
            });
            uploadArea.addEventListener('drop', (e) => {
                e.preventDefault();
                dragCounter = 0;
                uploadArea.classList.remove('drag-over');
                const files = e.dataTransfer.files;
                if (files.length > 0) {
                    handleFiles(files);
                }
            });

            // 点击上传区域也触发（label 已处理，但防止点到空白处无效）
            uploadArea.addEventListener('click', (e) => {
                // label 的 for 行为已覆盖，这里无需额外处理
            });

            // ── 进度更新 ──────────────────────
            function updateProgress() {
                const pct = totalFiles > 0 ? Math.round((finishedFiles / totalFiles) * 100) : 0;
                progressBar.style.width = pct + '%';
                taskCounter.textContent = `${finishedFiles}/${totalFiles}`;

                if (finishedFiles > 0 && startTime > 0) {
                    const elapsed = (Date.now() - startTime) / 1000;
                    const speed = elapsed > 0 ? (finishedFiles / elapsed).toFixed(2) : '—';
                    uploadSpeed.textContent = `${speed} 个/秒`;
                    const mins = Math.floor(elapsed / 60);
                    const secs = Math.floor(elapsed % 60);
                    elapsedTimeEl.textContent = mins > 0 ? `${mins}分${secs}秒` : `${secs}秒`;
                } else {
                    uploadSpeed.textContent = '—';
                    elapsedTimeEl.textContent = '—';
                }

                // 状态徽章
                if (totalFiles > 0 && finishedFiles === totalFiles) {
                    logStatus.textContent = '全部完成 ✅';
                    logStatus.className = 'badge success';
                } else if (totalFiles > 0 && finishedFiles > 0) {
                    logStatus.textContent = `上传中 ${finishedFiles}/${totalFiles}`;
                    logStatus.className = 'badge info';
                } else if (totalFiles > 0) {
                    logStatus.textContent = `待上传 ${totalFiles} 个`;
                    logStatus.className = 'badge warning';
                } else {
                    logStatus.textContent = '就绪';
                    logStatus.className = 'badge';
                }
            }

            // ── 开始上传 ──────────────────────
            async function startUpload() {
                if (isUploading) {
                    showToast('上传已在进行中', 'error');
                    return;
                }
                if (selectedFiles.length === 0) {
                    showToast('请先选择文件', 'error');
                    log('⚠ 请先选择文件');
                    return;
                }

                isUploading = true;
                btnUpload.disabled = true;
                btnUpload.textContent = '⏳ 上传中...';
                totalFiles = selectedFiles.length;
                finishedFiles = 0;
                startTime = Date.now();
                progressSection.style.display = 'block';
                updateProgress();
                log('🚀 开始上传 ' + totalFiles + ' 个文件...');
                logStatus.textContent = '上传中...';
                logStatus.className = 'badge info';

                const tasks = selectedFiles.map(async (f, index) => {
                    const fd = new FormData();
                    fd.append('image', f);
                    try {
                        const resp = await fetch('/upload', { method: 'POST', body: fd });
                        const json = await resp.json();
                        if (json.ok) {
                            finishedFiles++;
                            updateProgress();
                            log('✔ ' + f.name + '  ✅');
                        } else {
                            finishedFiles++;
                            updateProgress();
                            log('❌ ' + f.name + '  失败: ' + (json.error || '未知错误'));
                        }
                    } catch (e) {
                        finishedFiles++;
                        updateProgress();
                        log('❌ ' + f.name + '  网络错误: ' + e.message);
                    }
                });

                await Promise.all(tasks);
                isUploading = false;
                btnUpload.disabled = false;
                btnUpload.textContent = '⬆ 开始上传';
                log('✅ 批次上传结束');
                if (finishedFiles === totalFiles) {
                    log('🎉 所有文件上传成功！可以点击「停止服务」');
                    showToast('全部上传完成 🎉', 'success');
                    logStatus.textContent = '全部完成 ✅';
                    logStatus.className = 'badge success';
                } else {
                    log(`⚠ 完成 ${finishedFiles}/${totalFiles}，部分失败`);
                    logStatus.textContent = `完成 ${finishedFiles}/${totalFiles}`;
                    logStatus.className = 'badge warning';
                    showToast(`${finishedFiles}/${totalFiles} 完成`, '');
                }
            }

            // ── 停止服务 ──────────────────────
            async function shutdownServer() {
                if (isUploading) {
                    const confirmStop = confirm('上传正在进行中，确定要停止服务吗？');
                    if (!confirmStop) return;
                }
                log('🛑 正在停止服务...');
                btnStop.textContent = '⏳ 停止中...';
                btnStop.style.pointerEvents = 'none';
                btnStop.style.opacity = '0.7';
                try {
                    const resp = await fetch('/shutdown', { method: 'POST' });
                    const json = await resp.json();
                    log('✔ 服务已停止: ' + JSON.stringify(json));
                    logStatus.textContent = '服务已停止 – 正在处理照片';
                    logStatus.className = 'badge success';
                    showToast('服务已停止', 'success');
                } catch (e) {
                    log('❌ 停止失败: ' + e.message);
                    showToast('停止失败', 'error');
                } finally {
                    btnStop.textContent = '⏹ 停止服务';
                    btnStop.style.pointerEvents = 'auto';
                    btnStop.style.opacity = '1';
                }
                isUploading = false;
                btnUpload.disabled = false;
                btnUpload.textContent = '⬆ 开始上传';
            }

            // ── 自动日志 ──────────────────────
            function toggleAuto() {
                auto = !auto;
                if (auto) {
                    autoBtn.classList.add('active');
                    autoBtn.innerHTML = '📋 自动日志 (开)';
                    log('[AUTO] 开始轮询日志...');
                    timer = setInterval(async () => {
                        try {
                            const r = await fetch('/logs');
                            const j = await r.json();
                            log('[AUTO] ' + JSON.stringify(j));
                        } catch (e) {
                            log('[AUTO ERR] ' + e.message);
                        }
                    }, 3000);
                    showToast('自动日志已开启');
                } else {
                    autoBtn.classList.remove('active');
                    autoBtn.innerHTML = '📋 自动日志';
                    clearInterval(timer);
                    timer = null;
                    log('[AUTO] 停止轮询');
                    showToast('自动日志已关闭');
                }
            }

            // ── 页面卸载时清理 ────────────────
            window.addEventListener('beforeunload', () => {
                if (timer) clearInterval(timer);
            });

            // ── 暴露到全局 ────────────────────
            window.startUpload = startUpload;
            window.shutdownServer = shutdownServer;
            window.toggleAuto = toggleAuto;
            window.clearFiles = clearFiles;

            // ── 初始渲染 ──────────────────────
            renderFileList();
            logBox.textContent = '📋 就绪 — 请选择文件或拖拽到上方区域';
        })();
    </script>
</body>
</html>"""

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


    
