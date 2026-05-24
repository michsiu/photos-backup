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

JSON_FILE = Path("photos.json")

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}

# ======================
# LOG SYSTEM
# ======================
log_buffer = []
log_cursor = 0

def log(msg):
    ts = datetime.datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    log_buffer.append(line)

    if len(log_buffer) > 1000:
        log_buffer.pop(0)

# ======================
# LOAD DB
# ======================
if JSON_FILE.exists():
    photos_db = json.loads(JSON_FILE.read_text("utf-8"))
else:
    photos_db = {}

# ======================
# FRONTEND
# ======================
UPLOAD_PAGE = """
<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>Uploader</title>
<style>
body { font-family: sans-serif; max-width: 900px; margin: 30px auto; }
#logs { background:#111;color:#0f0;height:300px;overflow:auto;padding:10px;white-space:pre-wrap; }
button { margin-right:10px;padding:8px 12px; }
</style>
</head>
<body>

<h2>Photo Upload</h2>

<input type="file" id="file" multiple>
<br><br>

<button onclick="upload()">Upload</button>
<button onclick="toggleLogs()">Pause Logs</button>
<button onclick="stopServer()">STOP SERVER</button>

<pre id="logs"></pre>

<script>

let timer = null;

async function upload() {
    const files = document.getElementById('file').files;

    for (let f of files) {
        const fd = new FormData();
        fd.append('image', f);

        await fetch('/upload', { method: 'POST', body: fd });
    }
}

// ===== logs (diff mode) =====
async function fetchLogs() {
    const r = await fetch('/logs');
    const t = await r.text();

    if (t.trim().length === 0) return;

    const el = document.getElementById('logs');
    el.textContent += t + "\n";
    el.scrollTop = el.scrollHeight;
}

function startLogs() {
    if (timer) return;
    timer = setInterval(fetchLogs, 1000);
}

function stopLogs() {
    clearInterval(timer);
    timer = null;
}

function toggleLogs() {
    if (timer) {
        stopLogs();
    } else {
        startLogs();
    }
}

// ===== shutdown =====
async function stopServer() {
    await fetch('/shutdown', { method: 'POST' });
    alert("Server stopped");
}

startLogs();

</script>

</body>
</html>
"""

@app.route("/")
def index():
    return UPLOAD_PAGE

# ======================
# LOG API (diff)
# ======================
@app.route("/logs")
def logs():
    global log_cursor

    new_logs = log_buffer[log_cursor:]
    log_cursor = len(log_buffer)

    return "\n".join(new_logs)

# ======================
# EXIF
# ======================
def get_exif_date(data):
    try:
        exif = piexif.load(data)
        for ifd in ["Exif", "0th"]:
            for tag in [36867, 36868, 306]:
                if tag in exif.get(ifd, {}):
                    dt = exif[ifd][tag].decode()
                    return datetime.datetime.strptime(dt, "%Y:%m:%d %H:%M:%S")
    except:
        log("EXIF parse failed")
        print(traceback.format_exc())
    return None

# ======================
# UPLOAD
# ======================
@app.route("/upload", methods=["POST"])
def upload():
    try:
        file = request.files["image"]
        log(f"UPLOAD: {file.filename}")

        data = file.read()
        sha = hashlib.sha256(data).hexdigest()

        ext = os.path.splitext(file.filename)[1].lower()
        if ext not in ALLOWED_EXTENSIONS:
            log("INVALID FILE")
            return jsonify({"error": "bad ext"}), 400

        dt = get_exif_date(data) or datetime.datetime.utcnow()
        year = str(dt.year)

        photo_path = Path(f"photos/{year}/{sha}{ext}")
        thumb_path = Path(f"thumbs/{year}/{sha}{ext}")

        photo_path.parent.mkdir(parents=True, exist_ok=True)
        thumb_path.parent.mkdir(parents=True, exist_ok=True)

        with open(photo_path, "wb") as f:
            f.write(data)

        try:
            img = Image.open(io.BytesIO(data))
            img.thumbnail((400, 400))
            img.save(thumb_path)
        except:
            shutil.copy(photo_path, thumb_path)

        photos_db[sha] = {
            "file": file.filename,
            "path": str(photo_path)
        }

        JSON_FILE.write_text(json.dumps(photos_db, indent=2), encoding="utf-8")

        log("DONE")

        return jsonify({"ok": True})

    except Exception as e:
        log("ERROR")
        print(traceback.format_exc())
        return jsonify({"error": str(e)}), 500

# ======================
# SHUTDOWN (关键修复)
# ======================
@app.route("/shutdown", methods=["POST"])
def shutdown():
    log("SHUTDOWN REQUEST")

    # kill ngrok if exists
    os.system("pkill ngrok || true")
    os.system("pkill -f upload_server.py || true")

    func = request.environ.get("werkzeug.server.shutdown")
    if func:
        func()

    log("SERVER STOPPED")
    return "ok"

if __name__ == "__main__":
    log("SERVER START")
    app.run(host="0.0.0.0", port=5000, debug=False)