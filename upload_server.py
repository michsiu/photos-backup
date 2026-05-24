import os
import io
import json
import hashlib
import datetime
import shutil
import traceback

from pathlib import Path
from flask import Flask, request, jsonify
from PIL import Image
import piexif

app = Flask(__name__)

# =========================
# PATHS
# =========================
JSON_FILE = Path('photos.json')

ALLOWED_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.tiff'}

# =========================
# LOG SYSTEM (print + frontend buffer)
# =========================
log_buffer = []

def log(msg):
    ts = datetime.datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    log_buffer.append(line)
    if len(log_buffer) > 500:
        log_buffer.pop(0)

# =========================
# LOAD DB
# =========================
if JSON_FILE.exists():
    try:
        photos_db = json.loads(JSON_FILE.read_text(encoding='utf-8'))
    except Exception:
        log("❌ photos.json load failed")
        photos_db = {}
else:
    photos_db = {}

# =========================
# FRONTEND
# =========================
UPLOAD_PAGE = """
<!doctype html>
<html lang="zh">
<head>
<meta charset="utf-8">
<title>Uploader</title>

<style>
body { font-family: sans-serif; max-width: 900px; margin: 30px auto; }
button { padding: 10px 15px; margin-right: 10px; }
#logs {
    margin-top: 20px;
    background: #111;
    color: #0f0;
    padding: 10px;
    height: 300px;
    overflow-y: auto;
    white-space: pre-wrap;
    font-size: 12px;
}
</style>
</head>

<body>

<h2>📷 Photo Upload</h2>

<input type="file" id="file" multiple>
<br><br>

<button onclick="upload()">Upload</button>
<button onclick="toggleLogs()">🟢 Pause Logs</button>

<pre id="logs"></pre>

<script>

let timer = null;
let enabled = true;

async function upload() {
    const files = document.getElementById('file').files;

    for (let i = 0; i < files.length; i++) {
        const fd = new FormData();
        fd.append('image', files[i]);

        await fetch('/upload', {
            method: 'POST',
            body: fd
        });
    }
}

// ===== LOG POLLING =====
async function fetchLogs() {
    const r = await fetch('/logs');
    const t = await r.text();
    document.getElementById('logs').textContent = t;
}

// start polling
function startLogs() {
    if (timer) return;
    timer = setInterval(fetchLogs, 1000);
}

// stop polling
function stopLogs() {
    if (timer) {
        clearInterval(timer);
        timer = null;
    }
}

// toggle button
function toggleLogs() {
    enabled = !enabled;

    if (enabled) {
        startLogs();
        document.querySelector("button[onclick='toggleLogs()']").innerText = "🟢 Pause Logs";
    } else {
        stopLogs();
        document.querySelector("button[onclick='toggleLogs()']").innerText = "🔴 Resume Logs";
    }
}

// init
startLogs();

</script>

</body>
</html>
"""

# =========================
# ROUTES
# =========================
@app.route('/')
def index():
    return UPLOAD_PAGE

@app.route('/logs')
def logs():
    return "\n".join(log_buffer)

# =========================
# EXIF DATE
# =========================
def get_exif_date(image_bytes):
    try:
        exif = piexif.load(image_bytes)

        for ifd in ['Exif', '0th']:
            for tag in [36867, 36868, 306]:
                if tag in exif.get(ifd, {}):
                    dt = exif[ifd][tag].decode()
                    return datetime.datetime.strptime(dt, "%Y:%m:%d %H:%M:%S")

    except Exception:
        log("❌ EXIF parse failed")
        print(traceback.format_exc())

    return None

# =========================
# UPLOAD
# =========================
@app.route('/upload', methods=['POST'])
def upload():
    try:
        if 'image' not in request.files:
            log("❌ no file")
            return jsonify({"status": "error"}), 400

        file = request.files['image']

        log(f"📥 upload start: {file.filename}")

        data = file.read()

        size_mb = len(data) / 1024 / 1024
        log(f"📦 size: {size_mb:.2f} MB")

        sha = hashlib.sha256(data).hexdigest()
        log(f"🔐 sha256: {sha[:10]}...")

        ext = os.path.splitext(file.filename)[1].lower()

        if ext not in ALLOWED_EXTENSIONS:
            log("❌ unsupported type")
            return jsonify({"status": "error"}), 400

        dt = get_exif_date(data)

        if dt:
            log("📅 time source: EXIF")
        else:
            dt = datetime.datetime.utcnow()
            log("📅 time source: fallback UTC")

        year = str(dt.year)

        photo_path = Path(f"photos/{year}/{sha}{ext}")
        thumb_path = Path(f"thumbs/{year}/{sha}{ext}")

        photo_path.parent.mkdir(parents=True, exist_ok=True)
        thumb_path.parent.mkdir(parents=True, exist_ok=True)

        log(f"💾 saving -> {photo_path}")

        with open(photo_path, 'wb') as f:
            f.write(data)

        try:
            img = Image.open(io.BytesIO(data))
            img.thumbnail((400, 400))
            img.save(thumb_path)
            log("🖼 thumbnail OK")
        except Exception:
            log("⚠ thumbnail failed fallback copy")
            shutil.copy(photo_path, thumb_path)

        photos_db[sha] = {
            "file": file.filename,
            "path": str(photo_path),
            "thumb": str(thumb_path),
            "time": dt.isoformat()
        }

        JSON_FILE.write_text(
            json.dumps(photos_db, indent=2, ensure_ascii=False),
            encoding='utf-8'
        )

        log(f"✅ done: {file.filename}")

        return jsonify({"status": "ok", "sha256": sha})

    except Exception as e:
        log("❌ upload error")
        print(traceback.format_exc())
        return jsonify({"status": "error"}), 500

# =========================
# MAIN
# =========================
if __name__ == '__main__':
    log("🚀 server started")
    app.run(host='0.0.0.0', port=5000, debug=False)