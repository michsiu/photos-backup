import os
import zipfile
import io
import tempfile
import shutil
import threading
import time
from pathlib import Path
from flask import Flask, request, jsonify, send_from_directory

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
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
         background: #f4f6f9; color: #1e293b; padding: 32px 20px; max-width: 700px; margin: 0 auto; }
  .header { display: flex; align-items: center; gap: 12px; margin-bottom: 24px; }
  .header h1 { font-size: 2rem; font-weight: 700; }
  .card { background: white; border-radius: 24px; padding: 32px; box-shadow: 0 12px 32px rgba(0,0,0,0.06); margin-bottom: 24px; }

  /* 上传区域 - 无虚线，实线边框 */
  .upload-area { border: 2px solid #e2e8f0; border-radius: 16px; padding: 40px 20px; text-align: center;
                 background: #ffffff; cursor: pointer; transition: all 0.2s; margin-bottom: 16px; }
  .upload-area:hover { border-color: #6366f1; background: #f8fafc; }
  .upload-area input { display: none; }
  .upload-icon { font-size: 2.8rem; margin-bottom: 8px; }
  .upload-text { font-size: 1.2rem; font-weight: 600; color: #334155; }
  .upload-hint { font-size: 0.9rem; color: #94a3b8; margin-top: 6px; }

  /* 文件列表 */
  .file-list { margin-bottom: 16px; max-height: 150px; overflow-y: auto; }
  .file-item { padding: 6px 12px; background: #f1f5f9; border-radius: 8px; margin-bottom: 4px;
               font-size: 0.9rem; color: #475569; word-break: break-all; }

  .btn-group { display: flex; gap: 12px; flex-wrap: wrap; }
  button { padding: 12px 24px; border: none; border-radius: 12px; font-weight: 600; cursor: pointer;
           font-size: 1rem; transition: all 0.2s; display: inline-flex; align-items: center; gap: 8px; }
  .btn-upload { background: #4f46e5; color: white; }
  .btn-upload:hover { background: #4338ca; transform: translateY(-1px); box-shadow: 0 6px 16px rgba(79,70,229,0.3); }
  .btn-stop { background: #ef4444; color: white; }
  .btn-stop:hover { background: #dc2626; }
  .btn-auto { background: #e2e8f0; color: #334155; }
  .btn-auto.active { background: #6366f1; color: white; }

  .progress-section { margin-top: 20px; }
  .progress-bar-bg { background: #e2e8f0; border-radius: 10px; height: 10px; overflow: hidden; }
  .progress-bar-fill { background: #4f46e5; height: 100%; width: 0%; transition: width 0.3s; }
  .stats { display: flex; justify-content: space-between; margin-top: 10px; font-size: 0.9rem; color: #64748b; }

  #logBox { margin-top: 16px; background: #0f172a; color: #a7f3d0; padding: 16px; border-radius: 16px;
            height: 260px; overflow-y: auto; font-family: 'JetBrains Mono', Consolas, monospace; font-size: 0.8rem; line-height: 1.6; }
  .footer { margin-top: 12px; font-size: 0.85rem; color: #94a3b8; text-align: center; }
</style>
</head>
<body>
  <div class="header">
    <span style="font-size:2.5rem;">📷</span>
    <h1>Photo Upload</h1>
  </div>

  <div class="card">
    <!-- 上传区域（实线边框，美观） -->
    <label class="upload-area" id="uploadArea">
      <div class="upload-icon">⇧</div>
      <div class="upload-text">点击或拖拽文件到此处</div>
      <div class="upload-hint">支持 JPG, PNG, GIF, WEBP, ZIP</div>
      <input type="file" id="fileInput" multiple accept="image/*,.zip" />
    </label>

    <!-- 已选文件列表 -->
    <div class="file-list" id="fileList"></div>

    <div class="btn-group">
      <button class="btn-upload" onclick="startUpload()">⬆ 开始上传</button>
      <button class="btn-stop" onclick="shutdownServer()">⏹ 停止服务</button>
      <button class="btn-auto" id="autoBtn" onclick="toggleAuto()">📋 自动日志</button>
    </div>

    <!-- 进度区域 -->
    <div class="progress-section" id="progressSection" style="display:none;">
      <div class="progress-bar-bg">
        <div class="progress-bar-fill" id="progressBar"></div>
      </div>
      <div class="stats">
        <span id="taskCounter">0/0</span>
        <span id="uploadSpeed">—</span>
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
    let auto = false, timer;
    let totalFiles = 0, finishedFiles = 0;
    let startTime = 0;

    const progressSection = document.getElementById('progressSection');
    const progressBar = document.getElementById('progressBar');
    const taskCounter = document.getElementById('taskCounter');
    const uploadSpeed = document.getElementById('uploadSpeed');
    const logStatus = document.getElementById('logStatus');
    const fileInput = document.getElementById('fileInput');
    const fileList = document.getElementById('fileList');

    function log(msg) {
      const box = document.getElementById('logBox');
      box.textContent += msg + '\\n';
      box.scrollTop = box.scrollHeight;
    }

    // 初始提示
    log('📋 请选择文件或拖拽到上方区域');

    // 监听文件选择（包括拖拽后自动设置）
    fileInput.addEventListener('change', () => {
      const files = fileInput.files;
      fileList.innerHTML = '';
      if (files.length === 0) {
        log('未选择文件');
        return;
      }
      log(`已选择 ${files.length} 个文件:`);
      for (const f of files) {
        log(`  · ${f.name}`);
        const item = document.createElement('div');
        item.className = 'file-item';
        item.textContent = f.name;
        fileList.appendChild(item);
      }
    });

    function updateProgress() {
      const pct = totalFiles > 0 ? (finishedFiles / totalFiles * 100) : 0;
      progressBar.style.width = pct + '%';
      taskCounter.innerText = `${finishedFiles}/${totalFiles}`;

      if (finishedFiles > 0 && startTime > 0) {
        const elapsed = (Date.now() - startTime) / 1000;
        const speed = (finishedFiles / elapsed).toFixed(2);
        uploadSpeed.innerText = `${speed} 个/秒`;
      }

      if (totalFiles > 0 && finishedFiles === totalFiles) {
        logStatus.innerText = '全部上传完成 ✅';
      } else if (totalFiles > 0) {
        logStatus.innerText = `上传中 ${finishedFiles}/${totalFiles}`;
      }
    }

    // 拖拽支持（与之前相同，但会触发 input 的 change 事件）
    const uploadArea = document.getElementById('uploadArea');
    uploadArea.addEventListener('dragover', (e) => {
      e.preventDefault();
      uploadArea.style.borderColor = '#6366f1';
      uploadArea.style.background = '#f8fafc';
    });
    uploadArea.addEventListener('dragleave', () => {
      uploadArea.style.borderColor = '#e2e8f0';
      uploadArea.style.background = '#ffffff';
    });
    uploadArea.addEventListener('drop', (e) => {
      e.preventDefault();
      uploadArea.style.borderColor = '#e2e8f0';
      uploadArea.style.background = '#ffffff';
      const files = e.dataTransfer.files;
      fileInput.files = files;  // 这样会触发 change 事件
    });

    async function startUpload() {
      const files = fileInput.files;
      if (!files.length) {
        log('⚠ 请先选择文件');
        return;
      }

      totalFiles = files.length;
      finishedFiles = 0;
      startTime = Date.now();
      progressSection.style.display = 'block';
      updateProgress();
      log(`开始上传 ${totalFiles} 个文件...`);

      const tasks = Array.from(files).map(async (f) => {
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
          log('❌ ' + f.name + ' 网络错误: ' + e);
        }
      });

      await Promise.all(tasks);
      log('✅ 批次上传结束');
      if (finishedFiles === totalFiles) {
        log('🎉 所有文件上传成功，可以点击“停止服务”');
      }
    }

    async function shutdownServer() {
      log('🛑 正在停止服务...');
      try {
        const resp = await fetch('/shutdown', { method: 'POST' });
        const json = await resp.json();
        log('✔ 服务已停止: ' + JSON.stringify(json));
        logStatus.innerText = '服务已停止 – 正在处理照片';
      } catch (e) {
        log('❌ 停止失败: ' + e);
      }
    }

    function toggleAuto() {
      auto = !auto;
      const btn = document.getElementById('autoBtn');
      if (auto) {
        btn.classList.add('active');
        btn.innerHTML = '📋 自动日志 (开)';
        timer = setInterval(async () => {
          try {
            const r = await fetch('/logs');
            const j = await r.json();
            log('[AUTO] ' + JSON.stringify(j));
          } catch (e) { log('[AUTO ERR] ' + e); }
        }, 3000);
      } else {
        btn.classList.remove('active');
        btn.innerHTML = '📋 自动日志';
        clearInterval(timer);
      }
    }
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
    
# 静态文件服务：让浏览器可访问 photos 和 thumbs 目录
@app.route('/photos/<path:filename>')
def serve_photos(filename):
    return send_from_directory(PHOTO_DIR, filename)

@app.route('/thumbs/<path:filename>')
def serve_thumbs(filename):
    return send_from_directory(THUMB_DIR, filename)
    
@app.route('/api/photos')
def api_photos():
    with open(JSON_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)
    # 转换为列表方便前端处理，同时保留 key（sha256）
    photos_list = []
    for sha, info in data.items():
        item = dict(info)
        item['sha256'] = sha  # 确保有 sha256 字段
        photos_list.append(item)
    return jsonify(photos_list)
    


@app.route('/gallery')
def gallery():
    # 直接读 photos.json，把数据嵌入页面
    try:
        with open(JSON_FILE, 'r', encoding='utf-8') as f:
            photos_json = f.read()
    except Exception:
        photos_json = '{}'

    return f"""
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Photo Gallery</title>
  <style>
    * {{ margin:0; padding:0; box-sizing:border-box; }}
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
           background: #f4f6f9; color: #1e293b; padding: 20px; }}
    .container {{ max-width: 1200px; margin: 0 auto; }}
    h1 {{ font-size: 2rem; margin-bottom: 20px; text-align: center; }}
    .controls {{ display: flex; flex-wrap: wrap; gap: 12px; margin-bottom: 20px; align-items: center; }}
    .controls input, .controls select {{ padding: 8px 12px; border: 1px solid #cbd5e1; border-radius: 8px; font-size: 0.9rem; }}
    .controls input {{ flex: 1; min-width: 200px; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 16px; }}
    .card {{ background: white; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 12px rgba(0,0,0,0.06); transition: transform 0.2s; }}
    .card:hover {{ transform: translateY(-4px); }}
    .card img {{ width: 100%; height: 180px; object-fit: cover; display: block; }}
    .card-info {{ padding: 10px; font-size: 0.85rem; }}
    .card-info .name {{ font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
    .card-info .date {{ color: #64748b; font-size: 0.8rem; margin-top: 4px; }}
    .pagination {{ display: flex; justify-content: center; align-items: center; gap: 8px; margin: 24px 0; flex-wrap: wrap; }}
    .pagination button, .pagination span {{ padding: 6px 12px; border: 1px solid #cbd5e1; background: white; border-radius: 6px; cursor: pointer; }}
    .pagination button:disabled {{ opacity: 0.5; cursor: default; }}
    .pagination .active {{ background: #4f46e5; color: white; border-color: #4f46e5; }}
    #sentinel {{ height: 1px; }}
  </style>
</head>
<body>
<div class="container">
  <h1>📷 Photo Gallery</h1>
  
  <div class="controls">
    <input type="text" id="search" placeholder="🔍 搜索文件名..." oninput="resetAndRender()">
    <select id="yearFilter" onchange="resetAndRender()">
      <option value="">所有年份</option>
    </select>
    <select id="sortBy" onchange="resetAndRender()">
      <option value="date-desc" selected>时间 ↓ (默认)</option>
      <option value="date-asc">时间 ↑</option>
      <option value="name-asc">名称 A-Z</option>
      <option value="name-desc">名称 Z-A</option>
      <option value="random">随机</option>
    </select>
  </div>

  <div class="grid" id="grid"></div>
  <div class="pagination" id="pagination"></div>
  <div id="sentinel"></div>
</div>

<script>
  // 服务端直接注入数据，无需额外请求
  var ALL_PHOTOS_DATA = {photos_json};

  const PER_PAGE = 20;
  let allPhotos = [];
  let filteredPhotos = [];
  let currentPage = 1;
  let totalPages = 1;

  // 将 object 转成数组，并保留 sha256
  function initPhotos() {{
    const raw = ALL_PHOTOS_DATA;
    allPhotos = Object.keys(raw).map(sha => {{
      const item = raw[sha];
      item.sha256 = sha;
      return item;
    }});
    // 填充年份下拉
    const years = [...new Set(allPhotos.map(p => p.year))].sort();
    const yearSelect = document.getElementById('yearFilter');
    years.forEach(y => {{
      const opt = document.createElement('option');
      opt.value = y;
      opt.textContent = y;
      yearSelect.appendChild(opt);
    }});
    applyFilters();
  }}

  function applyFilters() {{
    const search = document.getElementById('search').value.toLowerCase();
    const year = document.getElementById('yearFilter').value;
    const sort = document.getElementById('sortBy').value;

    filteredPhotos = allPhotos.filter(p => {{
      const matchName = !search || p.fileName.toLowerCase().includes(search);
      const matchYear = !year || p.year === year;
      return matchName && matchYear;
    }});

    switch(sort) {{
      case 'date-asc':
        filteredPhotos.sort((a,b) => a.date.localeCompare(b.date));
        break;
      case 'date-desc':
        filteredPhotos.sort((a,b) => b.date.localeCompare(a.date));
        break;
      case 'name-asc':
        filteredPhotos.sort((a,b) => a.fileName.localeCompare(b.fileName));
        break;
      case 'name-desc':
        filteredPhotos.sort((a,b) => b.fileName.localeCompare(a.fileName));
        break;
      case 'random':
        for (let i = filteredPhotos.length - 1; i > 0; i--) {{
          const j = Math.floor(Math.random() * (i + 1));
          [filteredPhotos[i], filteredPhotos[j]] = [filteredPhotos[j], filteredPhotos[i]];
        }}
        break;
    }}

    totalPages = Math.ceil(filteredPhotos.length / PER_PAGE);
    currentPage = 1;
    renderPage();
    renderPagination();
  }}

  function resetAndRender() {{ applyFilters(); }}

  function getPagePhotos(page) {{
    const start = (page - 1) * PER_PAGE;
    return filteredPhotos.slice(start, start + PER_PAGE);
  }}

  function renderPage() {{
    const grid = document.getElementById('grid');
    grid.innerHTML = '';
    const pagePhotos = getPagePhotos(currentPage);
    pagePhotos.forEach(p => {{
      const card = document.createElement('div');
      card.className = 'card';
      const imgUrl = '/' + p.url;
      const thumbUrl = '/' + p.thumbnail;
      card.innerHTML = `
        <a href="${{imgUrl}}" target="_blank">
          <img src="${{thumbUrl}}" loading="lazy" alt="${{p.fileName}}">
        </a>
        <div class="card-info">
          <div class="name" title="${{p.fileName}}">${{p.fileName}}</div>
          <div class="date">${{p.date}}</div>
        </div>`;
      grid.appendChild(card);
    }});
  }}

  function renderPagination() {{
    const pagination = document.getElementById('pagination');
    pagination.innerHTML = '';
    if (totalPages <= 1) return;

    const createBtn = (text, page, disabled = false, cls = '') => {{
      const btn = document.createElement('button');
      btn.textContent = text;
      btn.disabled = disabled;
      btn.className = cls;
      btn.onclick = () => {{ goToPage(page); }};
      return btn;
    }};

    pagination.appendChild(createBtn('«', 1, currentPage === 1));
    pagination.appendChild(createBtn('‹', currentPage - 1, currentPage === 1));

    for (let i = 1; i <= totalPages; i++) {{
      const btn = createBtn(i, i, false, i === currentPage ? 'active' : '');
      pagination.appendChild(btn);
    }}

    pagination.appendChild(createBtn('›', currentPage + 1, currentPage === totalPages));
    pagination.appendChild(createBtn('»', totalPages, currentPage === totalPages));
  }}

  function goToPage(page) {{
    if (page < 1 || page > totalPages) return;
    currentPage = page;
    renderPage();
    renderPagination();
    window.scrollTo({{ top: 0, behavior: 'smooth' }});
  }}

  // 滚动自动加载
  const sentinel = document.getElementById('sentinel');
  const observer = new IntersectionObserver((entries) => {{
    if (entries[0].isIntersecting && currentPage < totalPages) {{
      currentPage++;
      renderPage();
      renderPagination();
    }}
  }}, {{ threshold: 0.1 }});
  observer.observe(sentinel);

  // 启动
  initPhotos();
</script>
</body>
</html>
"""

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)