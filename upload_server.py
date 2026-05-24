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
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">

<title>Photo Upload Pro</title>

<style>
:root{
  --bg:#0f172a;
  --card:#111827;
  --card2:#1e293b;
  --line:#334155;
  --text:#f8fafc;
  --muted:#94a3b8;
  --blue:#6366f1;
  --blue2:#4f46e5;
  --green:#10b981;
  --red:#ef4444;
  --yellow:#f59e0b;
  --shadow:0 10px 40px rgba(0,0,0,.35);
  --radius:22px;
}

*{
  margin:0;
  padding:0;
  box-sizing:border-box;
}

html,body{
  height:100%;
}

body{
  font-family:
    -apple-system,
    BlinkMacSystemFont,
    "Segoe UI",
    Roboto,
    sans-serif;

  background:
    radial-gradient(circle at top left,#1e1b4b 0%,transparent 35%),
    radial-gradient(circle at bottom right,#0f766e 0%,transparent 30%),
    var(--bg);

  color:var(--text);
  overflow-x:hidden;
}

/* ===== 顶部 ===== */

.topbar{
  position:sticky;
  top:0;
  z-index:100;
  backdrop-filter:blur(20px);
  background:rgba(15,23,42,.75);
  border-bottom:1px solid rgba(255,255,255,.05);
}

.topbar-inner{
  max-width:1100px;
  margin:auto;
  padding:18px 20px;
  display:flex;
  align-items:center;
  justify-content:space-between;
  gap:16px;
}

.brand{
  display:flex;
  align-items:center;
  gap:14px;
}

.brand-icon{
  width:54px;
  height:54px;
  border-radius:18px;
  background:linear-gradient(135deg,#6366f1,#8b5cf6);
  display:flex;
  align-items:center;
  justify-content:center;
  font-size:1.7rem;
  box-shadow:0 10px 25px rgba(99,102,241,.35);
}

.brand-text h1{
  font-size:1.35rem;
  font-weight:800;
}

.brand-text p{
  font-size:.82rem;
  color:var(--muted);
  margin-top:2px;
}

.status-pill{
  padding:10px 14px;
  border-radius:999px;
  background:rgba(255,255,255,.06);
  border:1px solid rgba(255,255,255,.06);
  color:#cbd5e1;
  font-size:.88rem;
  font-weight:600;
}

/* ===== 主区域 ===== */

.wrapper{
  max-width:1100px;
  margin:auto;
  padding:24px 20px 100px;
}

.grid{
  display:grid;
  grid-template-columns:1.3fr .9fr;
  gap:24px;
}

@media(max-width:900px){
  .grid{
    grid-template-columns:1fr;
  }
}

/* ===== 卡片 ===== */

.card{
  background:rgba(17,24,39,.82);
  border:1px solid rgba(255,255,255,.05);
  border-radius:var(--radius);
  box-shadow:var(--shadow);
  overflow:hidden;
}

.card-header{
  padding:22px 24px 18px;
  border-bottom:1px solid rgba(255,255,255,.05);
  display:flex;
  justify-content:space-between;
  align-items:center;
}

.card-title{
  font-size:1.05rem;
  font-weight:700;
}

.card-sub{
  color:var(--muted);
  font-size:.82rem;
  margin-top:3px;
}

.card-body{
  padding:24px;
}

/* ===== 上传区域 ===== */

.upload-area{
  position:relative;
  min-height:300px;
  border-radius:24px;
  overflow:hidden;
  cursor:pointer;

  border:2px solid rgba(255,255,255,.08);

  background:
    linear-gradient(180deg,rgba(99,102,241,.08),transparent),
    rgba(255,255,255,.02);

  transition:.25s;
}

.upload-area:hover{
  transform:translateY(-2px);
  border-color:rgba(99,102,241,.55);
  box-shadow:0 20px 50px rgba(99,102,241,.18);
}

.upload-area.dragging{
  border-color:#818cf8;
  background:
    linear-gradient(180deg,rgba(99,102,241,.18),transparent),
    rgba(255,255,255,.04);
}

.upload-inner{
  position:absolute;
  inset:0;
  display:flex;
  flex-direction:column;
  align-items:center;
  justify-content:center;
  text-align:center;
  padding:30px;
}

.upload-glow{
  width:110px;
  height:110px;
  border-radius:30px;
  background:
    radial-gradient(circle at 30% 30%,#a5b4fc,transparent 60%),
    linear-gradient(135deg,#4f46e5,#7c3aed);

  display:flex;
  align-items:center;
  justify-content:center;

  font-size:3rem;
  margin-bottom:24px;

  box-shadow:
    0 20px 60px rgba(99,102,241,.45),
    inset 0 0 30px rgba(255,255,255,.25);
}

.upload-title{
  font-size:1.5rem;
  font-weight:800;
}

.upload-desc{
  margin-top:10px;
  line-height:1.7;
  color:#cbd5e1;
}

.upload-tags{
  display:flex;
  flex-wrap:wrap;
  justify-content:center;
  gap:10px;
  margin-top:22px;
}

.tag{
  padding:8px 14px;
  border-radius:999px;
  background:rgba(255,255,255,.06);
  border:1px solid rgba(255,255,255,.08);
  color:#cbd5e1;
  font-size:.82rem;
}

.upload-area input{
  display:none;
}

/* ===== 文件区域 ===== */

.file-wrap{
  margin-top:24px;
}

.file-head{
  display:flex;
  justify-content:space-between;
  align-items:center;
  margin-bottom:14px;
}

.file-count{
  font-size:.92rem;
  color:#cbd5e1;
}

.file-size{
  font-size:.82rem;
  color:var(--muted);
}

.file-list{
  display:flex;
  flex-direction:column;
  gap:10px;

  max-height:320px;
  overflow:auto;
  padding-right:4px;
}

.file-list::-webkit-scrollbar{
  width:8px;
}

.file-list::-webkit-scrollbar-thumb{
  background:#334155;
  border-radius:999px;
}

.file-item{
  display:flex;
  align-items:center;
  gap:12px;

  padding:14px;
  border-radius:18px;

  background:
    linear-gradient(180deg,rgba(255,255,255,.04),transparent);

  border:1px solid rgba(255,255,255,.05);
}

.file-icon{
  width:46px;
  height:46px;
  border-radius:14px;
  background:rgba(99,102,241,.16);
  display:flex;
  align-items:center;
  justify-content:center;
  font-size:1.2rem;
  flex-shrink:0;
}

.file-info{
  flex:1;
  min-width:0;
}

.file-name{
  font-size:.92rem;
  font-weight:600;
  overflow:hidden;
  text-overflow:ellipsis;
  white-space:nowrap;
}

.file-meta{
  font-size:.78rem;
  color:var(--muted);
  margin-top:4px;
}

/* ===== 按钮 ===== */

.action-row{
  display:flex;
  flex-wrap:wrap;
  gap:14px;
  margin-top:26px;
}

.btn{
  border:none;
  border-radius:18px;
  padding:15px 22px;
  cursor:pointer;
  font-size:.96rem;
  font-weight:700;
  transition:.2s;
  display:flex;
  align-items:center;
  gap:10px;
}

.btn:hover{
  transform:translateY(-2px);
}

.btn-primary{
  background:linear-gradient(135deg,#6366f1,#4f46e5);
  color:white;
  box-shadow:0 12px 30px rgba(99,102,241,.35);
}

.btn-primary:hover{
  filter:brightness(1.05);
}

.btn-danger{
  background:linear-gradient(135deg,#ef4444,#dc2626);
  color:white;
  box-shadow:0 12px 30px rgba(239,68,68,.28);
}

.btn-secondary{
  background:rgba(255,255,255,.06);
  color:#e2e8f0;
  border:1px solid rgba(255,255,255,.08);
}

.btn-secondary.active{
  background:linear-gradient(135deg,#10b981,#059669);
  color:white;
  border:none;
  box-shadow:0 12px 30px rgba(16,185,129,.25);
}

/* ===== 统计 ===== */

.stats-grid{
  display:grid;
  grid-template-columns:repeat(2,1fr);
  gap:14px;
}

.stat-box{
  padding:18px;
  border-radius:20px;
  background:
    linear-gradient(180deg,rgba(255,255,255,.04),transparent);

  border:1px solid rgba(255,255,255,.05);
}

.stat-label{
  color:var(--muted);
  font-size:.8rem;
}

.stat-value{
  margin-top:10px;
  font-size:1.6rem;
  font-weight:800;
}

.progress-wrap{
  margin-top:22px;
}

.progress-top{
  display:flex;
  justify-content:space-between;
  margin-bottom:10px;
  font-size:.88rem;
}

.progress-bar{
  height:14px;
  background:rgba(255,255,255,.06);
  border-radius:999px;
  overflow:hidden;
}

.progress-fill{
  height:100%;
  width:0%;
  border-radius:999px;
  background:
    linear-gradient(90deg,#6366f1,#8b5cf6,#06b6d4);

  transition:width .25s;
}

/* ===== 日志 ===== */

.log-top{
  display:flex;
  justify-content:space-between;
  align-items:center;
  margin-bottom:16px;
}

.log-status{
  font-size:.82rem;
  color:#cbd5e1;
}

.log-box{
  background:#020617;
  border:1px solid rgba(255,255,255,.06);

  border-radius:20px;
  height:520px;
  overflow:auto;

  padding:20px;

  font-family:
    "JetBrains Mono",
    Consolas,
    monospace;

  font-size:.8rem;
  line-height:1.7;

  color:#86efac;
}

.log-box::-webkit-scrollbar{
  width:8px;
}

.log-box::-webkit-scrollbar-thumb{
  background:#334155;
  border-radius:999px;
}

.log-line{
  margin-bottom:4px;
  white-space:pre-wrap;
  word-break:break-word;
}

/* ===== 底部 ===== */

.footer{
  margin-top:28px;
  text-align:center;
  color:#94a3b8;
  font-size:.86rem;
  line-height:1.7;
}

/* ===== 动画 ===== */

@keyframes pulse{
  0%{transform:scale(1)}
  50%{transform:scale(1.04)}
  100%{transform:scale(1)}
}

.uploading .upload-glow{
  animation:pulse 1.6s infinite;
}
</style>
</head>

<body>

<div class="topbar">
  <div class="topbar-inner">

    <div class="brand">
      <div class="brand-icon">📷</div>

      <div class="brand-text">
        <h1>Photo Upload Pro</h1>
        <p>高性能图片上传与自动处理系统</p>
      </div>
    </div>

    <div class="status-pill" id="globalStatus">
      等待上传
    </div>

  </div>
</div>

<div class="wrapper">

  <div class="grid">

    <!-- 左侧 -->
    <div>

      <!-- 上传 -->
      <div class="card">

        <div class="card-header">
          <div>
            <div class="card-title">文件上传</div>
            <div class="card-sub">支持拖拽、批量上传、ZIP 压缩包</div>
          </div>
        </div>

        <div class="card-body">

          <label class="upload-area" id="uploadArea">

            <div class="upload-inner">

              <div class="upload-glow">
                ⇧
              </div>

              <div class="upload-title">
                点击或拖拽文件到此处
              </div>

              <div class="upload-desc">
                支持 JPG / PNG / GIF / WEBP / ZIP<br>
                可同时上传多个文件
              </div>

              <div class="upload-tags">
                <div class="tag">JPG</div>
                <div class="tag">PNG</div>
                <div class="tag">GIF</div>
                <div class="tag">WEBP</div>
                <div class="tag">ZIP</div>
              </div>

            </div>

            <input
              type="file"
              id="fileInput"
              multiple
              accept="image/*,.zip"
            />

          </label>

          <!-- 文件 -->
          <div class="file-wrap">

            <div class="file-head">
              <div class="file-count" id="fileCount">
                已选择 0 个文件
              </div>

              <div class="file-size" id="fileSize">
                0 MB
              </div>
            </div>

            <div class="file-list" id="fileList"></div>

          </div>

          <!-- 按钮 -->
          <div class="action-row">

            <button class="btn btn-primary" onclick="startUpload()">
              ⬆ 开始上传
            </button>

            <button class="btn btn-danger" onclick="shutdownServer()">
              ⏹ 停止服务
            </button>

            <button
              class="btn btn-secondary"
              id="autoBtn"
              onclick="toggleAuto()"
            >
              📋 自动日志
            </button>

          </div>

        </div>
      </div>

    </div>

    <!-- 右侧 -->
    <div>

      <!-- 统计 -->
      <div class="card">

        <div class="card-header">
          <div>
            <div class="card-title">上传状态</div>
            <div class="card-sub">实时任务监控</div>
          </div>
        </div>

        <div class="card-body">

          <div class="stats-grid">

            <div class="stat-box">
              <div class="stat-label">总文件</div>
              <div class="stat-value" id="statTotal">0</div>
            </div>

            <div class="stat-box">
              <div class="stat-label">已完成</div>
              <div class="stat-value" id="statDone">0</div>
            </div>

            <div class="stat-box">
              <div class="stat-label">上传速度</div>
              <div class="stat-value" id="statSpeed">—</div>
            </div>

            <div class="stat-box">
              <div class="stat-label">成功率</div>
              <div class="stat-value" id="statSuccess">0%</div>
            </div>

          </div>

          <div class="progress-wrap">

            <div class="progress-top">
              <span id="progressText">等待开始</span>
              <span id="progressPercent">0%</span>
            </div>

            <div class="progress-bar">
              <div class="progress-fill" id="progressFill"></div>
            </div>

          </div>

        </div>
      </div>

      <!-- 日志 -->
      <div class="card" style="margin-top:24px;">

        <div class="card-header">
          <div>
            <div class="card-title">系统日志</div>
            <div class="card-sub">实时输出运行信息</div>
          </div>
        </div>

        <div class="card-body">

          <div class="log-top">
            <div class="log-status" id="logStatus">
              就绪
            </div>

            <button
              class="btn btn-secondary"
              style="padding:10px 14px;font-size:.82rem;"
              onclick="clearLogs()"
            >
              清空日志
            </button>
          </div>

          <div class="log-box" id="logBox"></div>

        </div>

      </div>

    </div>

  </div>

  <div class="footer">
    上传完成后点击 <strong>停止服务</strong><br>
    系统将自动处理并提交到仓库
  </div>

</div>

<script>

let auto = false;
let timer = null;

let totalFiles = 0;
let finishedFiles = 0;
let successFiles = 0;
let failedFiles = 0;

let startTime = 0;

const fileInput = document.getElementById('fileInput');
const uploadArea = document.getElementById('uploadArea');

const fileList = document.getElementById('fileList');
const fileCount = document.getElementById('fileCount');
const fileSize = document.getElementById('fileSize');

const progressFill = document.getElementById('progressFill');
const progressPercent = document.getElementById('progressPercent');
const progressText = document.getElementById('progressText');

const statTotal = document.getElementById('statTotal');
const statDone = document.getElementById('statDone');
const statSpeed = document.getElementById('statSpeed');
const statSuccess = document.getElementById('statSuccess');

const logBox = document.getElementById('logBox');
const logStatus = document.getElementById('logStatus');
const globalStatus = document.getElementById('globalStatus');

function formatSize(bytes){
  if(bytes < 1024) return bytes + ' B';

  const kb = bytes / 1024;
  if(kb < 1024) return kb.toFixed(1) + ' KB';

  const mb = kb / 1024;
  if(mb < 1024) return mb.toFixed(1) + ' MB';

  const gb = mb / 1024;
  return gb.toFixed(2) + ' GB';
}

function log(msg){

  const line = document.createElement('div');
  line.className = 'log-line';

  const now = new Date();
  const time =
    now.toLocaleTimeString();

  line.textContent = '[' + time + '] ' + msg;

  logBox.appendChild(line);

  logBox.scrollTop = logBox.scrollHeight;
}

function clearLogs(){
  logBox.innerHTML = '';
  log('日志已清空');
}

function refreshStats(){

  statTotal.textContent = totalFiles;
  statDone.textContent = finishedFiles;

  const percent =
    totalFiles
      ? Math.round(finishedFiles / totalFiles * 100)
      : 0;

  progressFill.style.width = percent + '%';
  progressPercent.textContent = percent + '%';

  if(totalFiles > 0){
    progressText.textContent =
      finishedFiles + ' / ' + totalFiles;
  }else{
    progressText.textContent = '等待开始';
  }

  if(startTime && finishedFiles > 0){

    const sec =
      (Date.now() - startTime) / 1000;

    const speed =
      (finishedFiles / sec).toFixed(2);

    statSpeed.textContent =
      speed + '/s';
  }

  const successRate =
    totalFiles
      ? Math.round(successFiles / totalFiles * 100)
      : 0;

  statSuccess.textContent =
    successRate + '%';

  if(finishedFiles === totalFiles && totalFiles > 0){

    globalStatus.textContent = '上传完成';
    logStatus.textContent = '全部上传完成 ✅';

  }else if(totalFiles > 0){

    globalStatus.textContent =
      '上传中 ' +
      finishedFiles +
      '/' +
      totalFiles;

    logStatus.textContent =
      '上传中...';
  }
}

function buildFileList(files){

  fileList.innerHTML = '';

  let total = 0;

  for(const f of files){

    total += f.size || 0;

    const item =
      document.createElement('div');

    item.className = 'file-item';

    const ext =
      f.name.split('.').pop().toUpperCase();

    item.innerHTML = `
      <div class="file-icon">
        📄
      </div>

      <div class="file-info">

        <div class="file-name">
          ${f.name}
        </div>

        <div class="file-meta">
          ${ext} · ${formatSize(f.size || 0)}
        </div>

      </div>
    `;

    fileList.appendChild(item);
  }

  fileCount.textContent =
    '已选择 ' + files.length + ' 个文件';

  fileSize.textContent =
    formatSize(total);
}

fileInput.addEventListener('change', ()=>{

  const files = fileInput.files;

  if(!files.length){

    fileList.innerHTML = '';

    fileCount.textContent =
      '已选择 0 个文件';

    fileSize.textContent = '0 MB';

    log('未选择文件');

    return;
  }

  buildFileList(files);

  log('已选择 ' + files.length + ' 个文件');

  for(const f of files){
    log('  · ' + f.name);
  }
});

/* ===== 拖拽 ===== */

uploadArea.addEventListener('dragover',(e)=>{
  e.preventDefault();
  uploadArea.classList.add('dragging');
});

uploadArea.addEventListener('dragleave',()=>{
  uploadArea.classList.remove('dragging');
});

uploadArea.addEventListener('drop',(e)=>{

  e.preventDefault();

  uploadArea.classList.remove('dragging');

  const files = e.dataTransfer.files;

  fileInput.files = files;

  fileInput.dispatchEvent(
    new Event('change')
  );
});

/* ===== 上传 ===== */

async function startUpload(){

  const files = fileInput.files;

  if(!files.length){

    log('⚠ 请先选择文件');

    return;
  }

  totalFiles = files.length;
  finishedFiles = 0;
  successFiles = 0;
  failedFiles = 0;

  startTime = Date.now();

  document.body.classList.add('uploading');

  refreshStats();

  globalStatus.textContent =
    '准备上传';

  log('🚀 开始上传 ' + totalFiles + ' 个文件');

  const tasks =
    Array.from(files).map(async(file)=>{

      const fd = new FormData();

      fd.append('image',file);

      try{

        const resp = await fetch(
          '/upload',
          {
            method:'POST',
            body:fd
          }
        );

        const json = await resp.json();

        finishedFiles++;

        if(json.ok){

          successFiles++;

          log('✔ ' + file.name);

        }else{

          failedFiles++;

          log(
            '❌ ' +
            file.name +
            ' 失败: ' +
            (json.error || '未知错误')
          );
        }

        refreshStats();

      }catch(e){

        finishedFiles++;
        failedFiles++;

        refreshStats();

        log(
          '❌ ' +
          file.name +
          ' 网络错误: ' +
          e
        );
      }
    });

  await Promise.all(tasks);

  document.body.classList.remove('uploading');

  log('✅ 批次上传结束');

  if(successFiles === totalFiles){

    log('🎉 所有文件上传成功');
    log('👉 现在可以点击“停止服务”');

  }else{

    log(
      '⚠ 成功 ' +
      successFiles +
      ' 个，失败 ' +
      failedFiles +
      ' 个'
    );
  }
}

/* ===== 停止服务 ===== */

async function shutdownServer(){

  log('🛑 正在停止服务...');

  globalStatus.textContent =
    '停止中';

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
      JSON.stringify(json)
    );

    logStatus.textContent =
      '服务已停止';

    globalStatus.textContent =
      '已停止';

  }catch(e){

    log('❌ 停止失败: ' + e);

    globalStatus.textContent =
      '停止失败';
  }
}

/* ===== 自动日志 ===== */

function toggleAuto(){

  auto = !auto;

  const btn =
    document.getElementById('autoBtn');

  if(auto){

    btn.classList.add('active');

    btn.innerHTML =
      '📋 自动日志 (开)';

    log('📡 自动日志已开启');

    timer = setInterval(async()=>{

      try{

        const r =
          await fetch('/logs');

        const j =
          await r.json();

        log(
          '[AUTO] ' +
          JSON.stringify(j)
        );

      }catch(e){

        log(
          '[AUTO ERR] ' + e
        );
      }

    },3000);

  }else{

    btn.classList.remove('active');

    btn.innerHTML =
      '📋 自动日志';

    clearInterval(timer);

    log('📴 自动日志已关闭');
  }
}

/* ===== 初始化 ===== */

log('📋 系统初始化完成');
log('📂 请拖拽文件或点击上传区域');

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


    
