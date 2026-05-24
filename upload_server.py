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
  --bg:#f3f5fa;
  --card:#fff;
  --primary:#5b5fef;
  --primary2:#7c7ff6;
  --danger:#ef4444;
  --text:#0f172a;
  --sub:#64748b;
  --border:#e2e8f0;
  --shadow:0 10px 30px rgba(0,0,0,.06);
  --radius:22px;
}

*{
  margin:0;
  padding:0;
  box-sizing:border-box;
}

body{
  font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
  background:var(--bg);
  color:var(--text);
  min-height:100vh;
  padding:24px 14px 40px;
}

.container{
  width:100%;
  max-width:720px;
  margin:0 auto;
}

.header{
  display:flex;
  align-items:center;
  gap:14px;
  margin-bottom:20px;
}

.header-icon{
  width:54px;
  height:54px;
  border-radius:18px;
  background:linear-gradient(135deg,var(--primary),var(--primary2));
  display:flex;
  align-items:center;
  justify-content:center;
  font-size:28px;
  color:#fff;
  box-shadow:0 8px 20px rgba(91,95,239,.28);
  flex-shrink:0;
}

.header h1{
  font-size:28px;
  line-height:1.1;
  margin-bottom:4px;
}

.header p{
  color:var(--sub);
  font-size:14px;
}

.card{
  background:var(--card);
  border-radius:var(--radius);
  padding:22px;
  box-shadow:var(--shadow);
  margin-bottom:18px;
}

.upload-area{
  width:100%;
  border:2px dashed #d7deea;
  border-radius:20px;
  background:#f8fafc;
  padding:34px 18px;
  display:flex;
  flex-direction:column;
  align-items:center;
  justify-content:center;
  text-align:center;
  cursor:pointer;
  transition:.25s;
  margin-bottom:16px;
}

.upload-area:hover{
  border-color:var(--primary);
  background:#f5f7ff;
}

.upload-area.drag{
  border-color:var(--primary);
  background:#eef2ff;
  transform:scale(1.01);
}

.upload-area input{
  display:none;
}

.upload-icon{
  width:60px;
  height:60px;
  border-radius:50%;
  background:#eef2ff;
  display:flex;
  align-items:center;
  justify-content:center;
  font-size:30px;
  margin-bottom:14px;
}

.upload-title{
  font-size:19px;
  font-weight:700;
  line-height:1.4;
  margin-bottom:6px;
}

.upload-desc{
  font-size:14px;
  line-height:1.7;
  color:var(--sub);
  text-align:center;
  word-break:break-word;
}

.upload-tip{
  margin-top:12px;
  padding:7px 14px;
  border-radius:999px;
  background:#eef2f7;
  color:#64748b;
  font-size:12px;
  line-height:1.4;
}

.file-list{
  display:flex;
  flex-direction:column;
  gap:8px;
  max-height:180px;
  overflow-y:auto;
  margin-bottom:16px;
}

.file-item{
  display:flex;
  align-items:center;
  gap:12px;
  padding:12px;
  border-radius:14px;
  background:#f8fafc;
}

.file-icon{
  width:38px;
  height:38px;
  border-radius:12px;
  background:#eef2ff;
  display:flex;
  align-items:center;
  justify-content:center;
  flex-shrink:0;
}

.file-main{
  min-width:0;
  flex:1;
}

.file-name{
  font-size:14px;
  font-weight:600;
  overflow:hidden;
  text-overflow:ellipsis;
  white-space:nowrap;
  margin-bottom:3px;
}

.file-size{
  font-size:12px;
  color:var(--sub);
}

.btns{
  display:flex;
  gap:10px;
  flex-wrap:wrap;
}

button{
  border:none;
  cursor:pointer;
  border-radius:16px;
  font-size:15px;
  font-weight:700;
  padding:13px 18px;
  transition:.2s;
}

button:active{
  transform:scale(.97);
}

.btn-upload{
  flex:1;
  background:linear-gradient(135deg,var(--primary),var(--primary2));
  color:#fff;
}

.btn-upload:hover{
  transform:translateY(-1px);
}

.btn-stop{
  background:#fff1f2;
  color:#dc2626;
}

.btn-auto{
  background:#eef2ff;
  color:var(--primary);
}

.btn-auto.active{
  background:var(--primary);
  color:#fff;
}

.progress{
  margin-top:18px;
  display:none;
}

.progress-top{
  display:flex;
  justify-content:space-between;
  margin-bottom:8px;
  font-size:13px;
}

.progress-bar{
  height:10px;
  background:#e2e8f0;
  border-radius:999px;
  overflow:hidden;
}

.progress-fill{
  width:0%;
  height:100%;
  background:linear-gradient(90deg,var(--primary),var(--primary2));
  transition:.3s;
}

.stats{
  margin-top:10px;
  display:flex;
  justify-content:space-between;
  gap:10px;
  font-size:13px;
  color:var(--sub);
}

.log-header{
  display:flex;
  justify-content:space-between;
  align-items:center;
  margin-bottom:14px;
}

.log-title{
  font-size:16px;
  font-weight:700;
}

.status{
  font-size:12px;
  color:var(--sub);
  background:#f8fafc;
  padding:6px 12px;
  border-radius:999px;
}

.log{
  background:#0d1117;
  color:#c9d1d9;
  border-radius:18px;
  padding:16px;
  height:280px;
  overflow:auto;
  font-size:13px;
  line-height:1.7;
  font-family:Consolas,monospace;
  white-space:pre-wrap;
  word-break:break-word;
}

.footer{
  margin-top:6px;
  text-align:center;
  font-size:13px;
  color:#94a3b8;
  line-height:1.8;
}

@media (max-width:640px){

  .card{
    padding:16px;
  }

  .header h1{
    font-size:24px;
  }

  .upload-title{
    font-size:17px;
  }

  .upload-desc{
    font-size:13px;
    line-height:1.8;
    max-width:240px;
  }

  .btns{
    flex-direction:column;
  }

  .btn-upload,
  .btn-stop,
  .btn-auto{
    width:100%;
  }

  .stats{
    flex-direction:column;
    align-items:flex-start;
  }

  .log{
    height:220px;
  }
}
</style>
</head>

<body>

<div class="container">

  <div class="header">
    <div class="header-icon">📷</div>

    <div>
      <h1>Photo Upload</h1>
      <p>批量上传 · 自动处理 · 日志监控</p>
    </div>
  </div>

  <div class="card">

    <label class="upload-area" id="uploadArea">

      <div class="upload-icon">⇧</div>

      <div class="upload-title">
        点击或拖拽文件到此处
      </div>

      <div class="upload-desc">
        支持 JPG、PNG、GIF、WEBP、ZIP
      </div>

      <div class="upload-tip">
        📁 支持多选 · 拖拽上传
      </div>

      <input
        type="file"
        id="fileInput"
        multiple
        accept="image/*,.zip"
      >

    </label>

    <div class="file-list" id="fileList"></div>

    <div class="btns">

      <button
        class="btn-upload"
        id="uploadBtn"
      >
        ⬆ 开始上传
      </button>

      <button
        class="btn-stop"
        id="stopBtn"
      >
        ⏹ 停止服务
      </button>

      <button
        class="btn-auto"
        id="autoBtn"
      >
        📋 自动日志
      </button>

    </div>

    <div class="progress" id="progressSection">

      <div class="progress-top">
        <span id="taskCounter">0/0</span>
        <span id="progressText">0%</span>
      </div>

      <div class="progress-bar">
        <div class="progress-fill" id="progressFill"></div>
      </div>

      <div class="stats">
        <span id="speedText">—</span>
        <span id="statusText">等待上传</span>
      </div>

    </div>

  </div>

  <div class="card">

    <div class="log-header">
      <div class="log-title">📃 日志</div>
      <div class="status" id="logStatus">就绪</div>
    </div>

    <pre class="log" id="logBox"></pre>

  </div>

  <div class="footer">
    上传完成后点击「停止服务」<br>
    系统将自动处理并提交到仓库
  </div>

</div>

<script>

let autoMode = false;
let autoTimer = null;

let totalFiles = 0;
let finishedFiles = 0;
let startTime = 0;

const fileInput = document.getElementById('fileInput');
const fileList = document.getElementById('fileList');

const uploadArea = document.getElementById('uploadArea');

const progressSection = document.getElementById('progressSection');
const progressFill = document.getElementById('progressFill');
const progressText = document.getElementById('progressText');

const taskCounter = document.getElementById('taskCounter');
const speedText = document.getElementById('speedText');
const statusText = document.getElementById('statusText');

const logBox = document.getElementById('logBox');
const logStatus = document.getElementById('logStatus');

const uploadBtn = document.getElementById('uploadBtn');
const stopBtn = document.getElementById('stopBtn');
const autoBtn = document.getElementById('autoBtn');

function log(msg){

  const time = new Date().toLocaleTimeString();

  logBox.textContent += '[' + time + '] ' + msg + '\n';

  logBox.scrollTop = logBox.scrollHeight;
}

log('📋 页面已加载，等待选择文件');

function formatSize(bytes){

  if(bytes < 1024){
    return bytes + ' B';
  }

  if(bytes < 1024 * 1024){
    return (bytes / 1024).toFixed(1) + ' KB';
  }

  return (bytes / 1024 / 1024).toFixed(1) + ' MB';
}

function getIcon(name){

  const ext = name.split('.').pop().toLowerCase();

  if(ext === 'zip'){
    return '📦';
  }

  if(['jpg','jpeg','png','gif','webp','bmp'].includes(ext)){
    return '🖼';
  }

  return '📄';
}

function renderFiles(files){

  fileList.innerHTML = '';

  if(!files || !files.length){
    return;
  }

  for(const file of files){

    const item = document.createElement('div');
    item.className = 'file-item';

    item.innerHTML =
    '<div class="file-icon">' + getIcon(file.name) + '</div>' +
    '<div class="file-main">' +
      '<div class="file-name">' + file.name + '</div>' +
      '<div class="file-size">' + formatSize(file.size) + '</div>' +
    '</div>';

    fileList.appendChild(item);
  }

  log('📁 已选择 ' + files.length + ' 个文件');
}

fileInput.addEventListener('change', function(){

  renderFiles(fileInput.files);

});

uploadArea.addEventListener('dragover', function(e){

  e.preventDefault();

  uploadArea.classList.add('drag');

});

uploadArea.addEventListener('dragleave', function(){

  uploadArea.classList.remove('drag');

});

uploadArea.addEventListener('drop', function(e){

  e.preventDefault();

  uploadArea.classList.remove('drag');

  const dt = new DataTransfer();

  for(const file of e.dataTransfer.files){
    dt.items.add(file);
  }

  fileInput.files = dt.files;

  renderFiles(fileInput.files);

});

function updateProgress(){

  const percent =
    totalFiles > 0
    ? Math.round((finishedFiles / totalFiles) * 100)
    : 0;

  progressFill.style.width = percent + '%';

  progressText.textContent = percent + '%';

  taskCounter.textContent =
    finishedFiles + '/' + totalFiles;

  if(startTime){

    const elapsed =
      (Date.now() - startTime) / 1000;

    if(elapsed > 0){

      const speed =
        (finishedFiles / elapsed).toFixed(2);

      speedText.textContent =
        '⚡ ' + speed + ' 个/秒';
    }
  }

  if(percent === 100){

    statusText.textContent = '上传完成';

    logStatus.textContent = '全部完成 ✅';

  }else{

    statusText.textContent =
      '上传中 ' +
      finishedFiles +
      '/' +
      totalFiles;
  }
}

async function startUpload(){

  const files = fileInput.files;

  if(!files || !files.length){

    log('⚠ 请先选择文件');

    return;
  }

  totalFiles = files.length;
  finishedFiles = 0;

  startTime = Date.now();

  progressSection.style.display = 'block';

  logStatus.textContent = '上传中';

  updateProgress();

  log('🚀 开始上传');

  const tasks = [];

  for(const file of files){

    tasks.push(uploadSingle(file));

  }

  await Promise.all(tasks);

  log('✅ 批次上传结束');
}

async function uploadSingle(file){

  const fd = new FormData();

  fd.append('image', file);

  try{

    const resp = await fetch('/upload', {
      method:'POST',
      body:fd
    });

    const json = await resp.json();

    finishedFiles++;

    updateProgress();

    if(json.ok){

      log('✔ ' + file.name);

    }else{

      log('❌ ' + file.name + ' 上传失败');
    }

  }catch(err){

    finishedFiles++;

    updateProgress();

    log('❌ ' + file.name + ' 网络错误');
  }
}

async function shutdownServer(){

  log('🛑 正在停止服务...');

  try{

    const resp = await fetch('/shutdown', {
      method:'POST'
    });

    const json = await resp.json();

    log('✔ 服务已停止');

    logStatus.textContent = '服务已停止';

  }catch(err){

    log('❌ 停止失败: ' + err);

    logStatus.textContent = '停止失败';
  }
}

function toggleAuto(){

  autoMode = !autoMode;

  if(autoMode){

    autoBtn.classList.add('active');

    autoBtn.textContent = '📋 自动日志 (开)';

    log('📋 自动日志已开启');

    autoTimer = setInterval(async function(){

      try{

        const resp = await fetch('/logs');

        const json = await resp.json();

        log('[AUTO] ' + JSON.stringify(json));

      }catch(err){

        log('[AUTO ERR] ' + err);
      }

    },3000);

  }else{

    autoBtn.classList.remove('active');

    autoBtn.textContent = '📋 自动日志';

    clearInterval(autoTimer);

    autoTimer = null;

    log('📋 自动日志已关闭');
  }
}

uploadBtn.addEventListener('click', startUpload);

stopBtn.addEventListener('click', shutdownServer);

autoBtn.addEventListener('click', toggleAuto);

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


    
