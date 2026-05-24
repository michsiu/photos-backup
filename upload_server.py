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
:root{
    --bg:#f0f2f7;
    --card-bg:#ffffff;

    --primary:#5b5fef;
    --primary-hover:#4a4edb;
    --primary-light:#eef0ff;

    --danger:#f04438;
    --danger-hover:#d92d20;
    --danger-light:#fef3f2;

    --text:#1e293b;
    --text-secondary:#64748b;
    --text-muted:#94a3b8;

    --border:#e8ecf1;
    --border-hover:#c5c9d6;

    --upload-bg:#f9fafc;

    --shadow-sm:0 1px 2px rgba(0,0,0,.04);
    --shadow-md:0 8px 30px rgba(0,0,0,.06);
    --shadow-lg:0 16px 48px rgba(0,0,0,.08);
    --shadow-primary:0 8px 24px rgba(91,95,239,.28);

    --radius-sm:10px;
    --radius:16px;
    --radius-lg:20px;
    --radius-xl:24px;

    --font-mono:
        'SF Mono',
        'JetBrains Mono',
        'Fira Code',
        Consolas,
        Monaco,
        monospace;

    --transition:.2s cubic-bezier(.4,0,.2,1);
    --transition-spring:.35s cubic-bezier(.34,1.56,.64,1);
}

*{
    margin:0;
    padding:0;
    box-sizing:border-box;
}

html,body{
    min-height:100%;
}

body{
    font-family:
        -apple-system,
        BlinkMacSystemFont,
        "Segoe UI",
        Roboto,
        "Helvetica Neue",
        Arial,
        sans-serif;

    background:var(--bg);

    color:var(--text);

    padding:28px 16px 40px;

    display:flex;
    flex-direction:column;
    align-items:center;

    -webkit-font-smoothing:antialiased;
    -moz-osx-font-smoothing:grayscale;

    background-image:
        radial-gradient(
            ellipse at 30% 10%,
            rgba(91,95,239,.04) 0%,
            transparent 60%
        ),
        radial-gradient(
            ellipse at 70% 90%,
            rgba(91,95,239,.03) 0%,
            transparent 60%
        );
}

.container{
    width:100%;
    max-width:680px;

    display:flex;
    flex-direction:column;
    gap:20px;
}

/* Header */

.header{
    display:flex;
    align-items:center;
    gap:14px;
    padding:4px 0;
}

.header-icon{
    width:50px;
    height:50px;

    border-radius:16px;

    background:
        linear-gradient(
            135deg,
            #5b5fef 0%,
            #7c7ff6 100%
        );

    display:flex;
    align-items:center;
    justify-content:center;

    font-size:1.6rem;

    box-shadow:
        0 6px 18px rgba(91,95,239,.22);

    flex-shrink:0;
}

.header-info h1{
    font-size:1.55rem;
    font-weight:700;

    color:#1e293b;

    letter-spacing:-.02em;

    line-height:1.2;
}

.header-info span{
    font-size:.82rem;
    color:var(--text-secondary);
    font-weight:500;
}

/* Card */

.card{
    background:var(--card-bg);

    border-radius:var(--radius-xl);

    padding:28px;

    box-shadow:var(--shadow-md);

    border:1px solid var(--border);

    transition:box-shadow var(--transition);
}

.card:hover{
    box-shadow:var(--shadow-lg);
}

/* Upload Area */

.upload-area{
    display:flex;
    flex-direction:column;
    align-items:center;
    justify-content:center;

    gap:12px;

    border:2px dashed #dde1e9;

    border-radius:var(--radius-lg);

    padding:42px 24px;

    background:var(--upload-bg);

    cursor:pointer;

    transition:all var(--transition-spring);

    position:relative;

    overflow:hidden;

    user-select:none;

    -webkit-tap-highlight-color:transparent;

    margin-bottom:14px;

    min-height:240px;
}

.upload-area::before{
    content:'';

    position:absolute;
    inset:0;

    background:
        radial-gradient(
            circle at 50% 0%,
            rgba(91,95,239,.04) 0%,
            transparent 60%
        );

    opacity:0;

    transition:opacity var(--transition);

    pointer-events:none;
}

.upload-area:hover{
    border-color:#bcc1d8;

    background:#f6f7fb;

    transform:translateY(-1px);

    box-shadow:
        0 4px 16px rgba(91,95,239,.06);
}

.upload-area:hover::before{
    opacity:1;
}

.upload-area.dragover{
    border-color:var(--primary)!important;

    background:var(--primary-light)!important;

    transform:scale(1.01);

    box-shadow:
        0 8px 28px rgba(91,95,239,.14);
}

.upload-area input{
    display:none;
}

.upload-icon-wrap{
    width:64px;
    height:64px;

    border-radius:50%;

    background:#eef0ff;

    display:flex;
    align-items:center;
    justify-content:center;

    font-size:1.9rem;

    margin-bottom:4px;

    transition:all var(--transition-spring);

    pointer-events:none;

    flex-shrink:0;
}

.upload-area.dragover .upload-icon-wrap{
    transform:scale(1.08);
    background:#dde0ff;
}

.upload-text{
    font-size:1.15rem;

    font-weight:700;

    color:#334155;

    line-height:1.5;

    text-align:center;

    pointer-events:none;

    transition:color var(--transition);

    max-width:100%;
}

.upload-hint{
    font-size:.92rem;

    color:var(--text-muted);

    line-height:1.8;

    text-align:center;

    margin-top:0;

    pointer-events:none;

    transition:color var(--transition);

    max-width:100%;
}

.upload-badge{
    display:inline-flex;

    align-items:center;

    justify-content:center;

    gap:6px;

    font-size:.78rem;

    line-height:1.2;

    color:var(--text-muted);

    background:#f1f5f9;

    border-radius:999px;

    padding:8px 14px;

    margin-top:2px;

    pointer-events:none;

    letter-spacing:.02em;

    white-space:nowrap;
}

.upload-badge span{
    font-weight:600;
}

/* File List */

.file-list{
    margin-bottom:14px;

    max-height:170px;

    overflow-y:auto;

    display:flex;
    flex-direction:column;
    gap:6px;
}

.file-list:empty{
    display:none;
}

.file-item{
    display:flex;
    align-items:center;
    gap:10px;

    padding:10px 14px;

    background:#f8fafc;

    border-radius:var(--radius-sm);

    border:1px solid transparent;

    transition:all var(--transition);
}

.file-item:hover{
    background:#f1f5f9;
    border-color:#e2e8f0;
}

.file-item-icon{
    width:34px;
    height:34px;

    border-radius:8px;

    display:flex;
    align-items:center;
    justify-content:center;

    background:#eef0ff;

    color:var(--primary);

    flex-shrink:0;
}

.file-item-info{
    flex:1;
    min-width:0;

    display:flex;
    flex-direction:column;
}

.file-item-name{
    font-size:.88rem;
    font-weight:500;

    color:#334155;

    white-space:nowrap;
    overflow:hidden;
    text-overflow:ellipsis;
}

.file-item-size{
    font-size:.75rem;
    color:var(--text-muted);
}

.file-item-badge{
    flex-shrink:0;

    font-size:.7rem;

    padding:3px 8px;

    border-radius:12px;

    background:#e2e8f0;

    color:#64748b;

    text-transform:uppercase;
}

/* Buttons */

.btn-group{
    display:flex;
    gap:10px;
    flex-wrap:wrap;
}

button{
    padding:11px 22px;

    border:none;

    border-radius:var(--radius);

    font-weight:600;

    cursor:pointer;

    font-size:.93rem;

    transition:all var(--transition-spring);

    display:inline-flex;
    align-items:center;
    justify-content:center;

    gap:7px;

    white-space:nowrap;
}

button:active{
    transform:scale(.96);
}

.btn-upload{
    background:var(--primary);

    color:#fff;

    flex:1 1 auto;

    min-width:130px;

    box-shadow:
        0 4px 14px rgba(91,95,239,.25);
}

.btn-upload:hover{
    background:var(--primary-hover);

    transform:translateY(-2px);

    box-shadow:var(--shadow-primary);
}

.btn-stop{
    background:#fff;

    color:var(--danger);

    border:1.5px solid #fecaca;
}

.btn-stop:hover{
    background:var(--danger-light);

    border-color:var(--danger);
}

.btn-auto{
    background:#f8fafc;

    color:#475569;

    border:1.5px solid #e2e8f0;
}

.btn-auto.active{
    background:var(--primary-light);

    color:var(--primary);

    border-color:#c5c9f6;
}

.dot-indicator{
    width:7px;
    height:7px;

    border-radius:50%;

    background:#c5c9d6;
}

.btn-auto.active .dot-indicator{
    background:var(--primary);
}

/* Progress */

.progress-section{
    margin-top:18px;
}

.progress-header{
    display:flex;
    justify-content:space-between;
    align-items:center;

    margin-bottom:8px;
}

.progress-label{
    font-size:.8rem;
    font-weight:600;

    color:var(--text-secondary);

    text-transform:uppercase;
}

.progress-pct{
    font-size:.85rem;
    font-weight:700;

    color:var(--primary);

    font-family:var(--font-mono);
}

.progress-bar-bg{
    background:#e8ecf1;

    border-radius:20px;

    height:8px;

    overflow:hidden;
}

.progress-bar-fill{
    background:
        linear-gradient(
            90deg,
            #5b5fef 0%,
            #7c7ff6 100%
        );

    height:100%;

    width:0%;

    border-radius:20px;

    transition:width .35s ease;
}

.progress-bar-fill.complete{
    background:
        linear-gradient(
            90deg,
            #22c55e 0%,
            #4ade80 100%
        );
}

.stats{
    display:flex;
    justify-content:space-between;
    align-items:center;

    margin-top:8px;

    gap:12px;

    font-size:.82rem;

    color:var(--text-secondary);
}

.stat-item{
    display:flex;
    align-items:center;
    gap:5px;

    font-family:var(--font-mono);
}

.stat-dot{
    width:6px;
    height:6px;

    border-radius:50%;

    background:#22c55e;
}

.stat-dot.idle{
    background:#c5c9d6;
}

/* Completion */

.completion-banner{
    display:none;

    align-items:center;
    gap:10px;

    padding:12px 18px;

    border-radius:var(--radius);

    background:#f0fdf4;

    border:1px solid #bbf7d0;

    color:#16a34a;

    font-weight:600;

    font-size:.9rem;

    margin-top:12px;
}

.completion-banner.show{
    display:flex;
}

/* Log */

.log-card-header{
    display:flex;
    justify-content:space-between;
    align-items:center;

    margin-bottom:14px;
}

.log-card-title{
    font-weight:700;

    font-size:.95rem;

    color:#334155;

    display:flex;
    align-items:center;
    gap:8px;
}

#logStatus{
    font-size:.76rem;

    color:var(--text-muted);

    font-weight:500;

    padding:4px 12px;

    border-radius:20px;

    background:#f8fafc;

    border:1px solid #e8ecf1;
}

#logStatus.done{
    color:#16a34a;
    background:#f0fdf4;
}

#logStatus.error{
    color:#dc2626;
    background:#fef2f2;
}

#logStatus.active{
    color:var(--primary);
    background:var(--primary-light);
}

#logBox{
    background:#0d1117;

    color:#c9d1d9;

    padding:18px;

    border-radius:var(--radius);

    height:270px;

    overflow-y:auto;

    font-family:var(--font-mono);

    font-size:.78rem;

    line-height:1.7;

    white-space:pre-wrap;

    word-break:break-word;
}

.log-line-success{
    color:#7ee787;
}

.log-line-error{
    color:#ffa198;
}

.log-line-info{
    color:#a5d6ff;
}

.log-line-warn{
    color:#f0c062;
}

/* Footer */

.footer{
    text-align:center;

    font-size:.82rem;

    color:var(--text-muted);
}

.footer strong{
    color:var(--text-secondary);
}

.footer-dot{
    display:inline-block;

    width:5px;
    height:5px;

    border-radius:50%;

    background:#c5c9d6;

    margin:0 8px;
}

/* Mobile */

@media (max-width:600px){

    body{
        padding:16px 10px 28px;
    }

    .container{
        gap:14px;
    }

    .card{
        padding:20px 16px;
    }

    .upload-area{
        padding:34px 18px;

        min-height:220px;

        gap:10px;
    }

    .upload-text{
        font-size:1rem;
        line-height:1.55;
    }

    .upload-hint{
        font-size:.84rem;
        line-height:1.7;
    }

    .upload-badge{
        font-size:.72rem;
        padding:7px 12px;
    }

    .upload-icon-wrap{
        width:52px;
        height:52px;

        font-size:1.5rem;

        margin-bottom:2px;
    }

    .header-icon{
        width:40px;
        height:40px;

        font-size:1.3rem;
    }

    .header-info h1{
        font-size:1.3rem;
    }

    button{
        padding:10px 16px;
        font-size:.86rem;
    }

    .btn-upload{
        min-width:100%;
    }

    #logBox{
        height:200px;
        font-size:.72rem;
        padding:14px;
    }

    .stats{
        flex-direction:column;
        align-items:flex-start;
        gap:4px;
    }
}

@media (max-width:380px){

    .btn-group{
        flex-direction:column;
    }

    .btn-stop,
    .btn-auto{
        width:100%;
    }

    .upload-area{
        padding:26px 14px;
    }
}
</style>
</head>

<body>

<div class="container">

    <div class="header">
        <div class="header-icon">📷</div>

        <div class="header-info">
            <h1>Photo Upload</h1>
            <span>批量上传 · 自动处理</span>
        </div>
    </div>

    <!-- Main Card -->

    <div class="card">

        <label class="upload-area" id="uploadArea">

            <div class="upload-icon-wrap">
                ⇧
            </div>

            <div class="upload-text">
                点击或拖拽文件到此处
            </div>

            <div class="upload-hint">
                支持 JPG · PNG · GIF · WEBP · ZIP
            </div>

            <div class="upload-badge">
                📁 可多选
                <span>·</span>
                拖拽也行
            </div>

            <input
                type="file"
                id="fileInput"
                multiple
                accept="image/*,.zip"
            />

        </label>

        <!-- File List -->

        <div class="file-list" id="fileList"></div>

        <!-- Buttons -->

        <div class="btn-group">

            <button
                class="btn-upload"
                onclick="startUpload()"
            >
                ⬆ 开始上传
            </button>

            <button
                class="btn-stop"
                onclick="shutdownServer()"
            >
                ⏹ 停止服务
            </button>

            <button
                class="btn-auto"
                id="autoBtn"
                onclick="toggleAuto()"
            >
                <span class="dot-indicator"></span>
                自动日志
            </button>

        </div>

        <!-- Progress -->

        <div
            class="progress-section"
            id="progressSection"
            style="display:none;"
        >

            <div class="progress-header">
                <span class="progress-label">
                    上传进度
                </span>

                <span
                    class="progress-pct"
                    id="progressPct"
                >
                    0%
                </span>
            </div>

            <div class="progress-bar-bg">
                <div
                    class="progress-bar-fill"
                    id="progressBar"
                ></div>
            </div>

            <div class="stats">

                <span class="stat-item">

                    <span
                        class="stat-dot idle"
                        id="statDot"
                    ></span>

                    <span id="taskCounter">
                        0/0
                    </span>

                </span>

                <span
                    class="stat-item"
                    id="uploadSpeed"
                >
                    —
                </span>

            </div>

        </div>

        <!-- Completion -->

        <div
            class="completion-banner"
            id="completionBanner"
        >
            🎉 所有文件上传成功，可以点击「停止服务」
        </div>

    </div>

    <!-- Log -->

    <div class="card">

        <div class="log-card-header">

            <span class="log-card-title">
                📃 日志
            </span>

            <span id="logStatus">
                就绪
            </span>

        </div>

        <pre id="logBox"></pre>

    </div>

    <!-- Footer -->

    <div class="footer">
        上传完成后点击
        <strong>停止服务</strong>

        <span class="footer-dot"></span>

        系统将自动处理并提交到仓库
    </div>

</div>

<script>

(function(){

    let auto = false;
    let timer;

    let totalFiles = 0;
    let finishedFiles = 0;

    let startTime = 0;

    const progressSection =
        document.getElementById('progressSection');

    const progressBar =
        document.getElementById('progressBar');

    const progressPct =
        document.getElementById('progressPct');

    const taskCounter =
        document.getElementById('taskCounter');

    const uploadSpeed =
        document.getElementById('uploadSpeed');

    const statDot =
        document.getElementById('statDot');

    const logStatus =
        document.getElementById('logStatus');

    const fileInput =
        document.getElementById('fileInput');

    const fileList =
        document.getElementById('fileList');

    const completionBanner =
        document.getElementById('completionBanner');

    const uploadArea =
        document.getElementById('uploadArea');

    function formatSize(bytes){

        if(bytes < 1024){
            return bytes + ' B';
        }

        if(bytes < 1048576){
            return (
                bytes / 1024
            ).toFixed(1) + ' KB';
        }

        return (
            bytes / 1048576
        ).toFixed(1) + ' MB';
    }

    function fileIcon(name){

        const ext =
            name
            .split('.')
            .pop()
            .toLowerCase();

        const map = {
            jpg:'🖼',
            jpeg:'🖼',
            png:'🖼',
            gif:'🎞',
            webp:'🖼',
            zip:'📦'
        };

        return map[ext] || '📄';
    }

    function log(msg,type){

        const box =
            document.getElementById('logBox');

        const className =
            type === 'success'
            ? 'log-line-success'
            : type === 'error'
            ? 'log-line-error'
            : type === 'warn'
            ? 'log-line-warn'
            : type === 'info'
            ? 'log-line-info'
            : '';

        const line =
            className
            ? `<span class="${className}">${msg}</span>`
            : msg;

        box.innerHTML += line + '\n';

        box.scrollTop =
            box.scrollHeight;
    }

    log(
        '📋 准备就绪 — 请选择文件或拖拽到上方区域',
        'info'
    );

    function renderFileList(files){

        fileList.innerHTML = '';

        if(!files || !files.length){
            return;
        }

        for(const f of files){

            const item =
                document.createElement('div');

            item.className =
                'file-item';

            const ext =
                f.name
                .split('.')
                .pop()
                .toLowerCase();

            item.innerHTML = `
                <div class="file-item-icon">
                    ${fileIcon(f.name)}
                </div>

                <div class="file-item-info">

                    <span class="file-item-name">
                        ${f.name}
                    </span>

                    <span class="file-item-size">
                        ${formatSize(f.size)}
                    </span>

                </div>

                <span class="file-item-badge">
                    ${ext}
                </span>
            `;

            fileList.appendChild(item);
        }

        log(
            '📋 已选择 ' +
            files.length +
            ' 个文件',
            'info'
        );
    }

    fileInput.addEventListener(
        'change',
        ()=>{
            renderFileList(fileInput.files);
        }
    );

    function updateProgress(){

        const pct =
            totalFiles > 0
            ? Math.round(
                finishedFiles /
                totalFiles *
                100
            )
            : 0;

        progressBar.style.width =
            pct + '%';

        progressPct.textContent =
            pct + '%';

        taskCounter.textContent =
            finishedFiles +
            '/' +
            totalFiles;

        if(
            totalFiles > 0 &&
            finishedFiles === totalFiles
        ){

            progressBar.classList.add(
                'complete'
            );

            logStatus.textContent =
                '全部完成 ✅';

            logStatus.className =
                'done';

        }else{

            progressBar.classList.remove(
                'complete'
            );
        }

        if(
            finishedFiles > 0 &&
            startTime > 0
        ){

            const elapsed =
                (
                    Date.now() -
                    startTime
                ) / 1000;

            const speed =
                (
                    finishedFiles /
                    elapsed
                ).toFixed(2);

            uploadSpeed.textContent =
                '⚡ ' +
                speed +
                ' 个/秒';
        }
    }

    uploadArea.addEventListener(
        'dragover',
        (e)=>{
            e.preventDefault();
            uploadArea.classList.add(
                'dragover'
            );
        }
    );

    uploadArea.addEventListener(
        'dragleave',
        ()=>{
            uploadArea.classList.remove(
                'dragover'
            );
        }
    );

    uploadArea.addEventListener(
        'drop',
        (e)=>{

            e.preventDefault();

            uploadArea.classList.remove(
                'dragover'
            );

            const files =
                e.dataTransfer.files;

            fileInput.files = files;

            fileInput.dispatchEvent(
                new Event('change')
            );
        }
    );

    async function startUpload(){

        const files =
            fileInput.files;

        if(!files.length){

            log(
                '⚠ 请先选择文件',
                'warn'
            );

            return;
        }

        totalFiles =
            files.length;

        finishedFiles = 0;

        startTime = Date.now();

        progressSection.style.display =
            'block';

        completionBanner.classList.remove(
            'show'
        );

        updateProgress();

        log(
            '🚀 开始上传 ' +
            totalFiles +
            ' 个文件...',
            'info'
        );

        const tasks =
            Array.from(files)
            .map(async(f)=>{

                const fd =
                    new FormData();

                fd.append(
                    'image',
                    f
                );

                try{

                    const resp =
                        await fetch(
                            '/upload',
                            {
                                method:'POST',
                                body:fd
                            }
                        );

                    const json =
                        await resp.json();

                    finishedFiles++;

                    updateProgress();

                    if(json.ok){

                        log(
                            '✔ ' +
                            f.name,
                            'success'
                        );

                    }else{

                        log(
                            '❌ ' +
                            f.name,
                            'error'
                        );
                    }

                }catch(e){

                    finishedFiles++;

                    updateProgress();

                    log(
                        '❌ ' +
                        f.name +
                        ' 网络错误',
                        'error'
                    );
                }
            });

        await Promise.all(tasks);

        completionBanner.classList.add(
            'show'
        );

        log(
            '🎉 所有文件上传成功',
            'success'
        );
    }

    async function shutdownServer(){

        log(
            '🛑 正在停止服务...',
            'warn'
        );

        try{

            const resp =
                await fetch(
                    '/shutdown',
                    {
                        method:'POST'
                    }
                );

            const json =
                await resp.json();

            log(
                '✔ 服务已停止: ' +
                JSON.stringify(json),
                'success'
            );

        }catch(e){

            log(
                '❌ 停止失败',
                'error'
            );
        }
    }

    function toggleAuto(){

        auto = !auto;

        const btn =
            document.getElementById(
                'autoBtn'
            );

        if(auto){

            btn.classList.add(
                'active'
            );

            btn.innerHTML =
                '<span class="dot-indicator"></span> 自动日志 (开)';

            timer =
                setInterval(async()=>{

                    try{

                        const r =
                            await fetch(
                                '/logs'
                            );

                        const j =
                            await r.json();

                        log(
                            '[AUTO] ' +
                            JSON.stringify(j),
                            'info'
                        );

                    }catch(e){

                        log(
                            '[AUTO ERR]',
                            'error'
                        );
                    }

                },3000);

        }else{

            btn.classList.remove(
                'active'
            );

            btn.innerHTML =
                '<span class="dot-indicator"></span> 自动日志';

            clearInterval(timer);
        }
    }

    window.startUpload =
        startUpload;

    window.shutdownServer =
        shutdownServer;

    window.toggleAuto =
        toggleAuto;

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


    
