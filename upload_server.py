import os
import io
import json
import hashlib
import datetime
import shutil
import traceback
import signal
from pathlib import Path
from flask import Flask, request, jsonify
from PIL import Image

app = Flask(__name__)

# =========================
# PATH FIX
# =========================
BASE_DIR = Path(__file__).resolve().parent

PHOTO_DIR = BASE_DIR / "photos"
THUMB_DIR = BASE_DIR / "thumbs"
JSON_FILE = BASE_DIR / "photos.json"

PHOTO_DIR.mkdir(parents=True, exist_ok=True)
THUMB_DIR.mkdir(parents=True, exist_ok=True)

# =========================
# DB
# =========================
if JSON_FILE.exists():
    photos_db = json.loads(JSON_FILE.read_text(encoding="utf-8"))
else:
    photos_db = {}

def log(msg):
    print(f"[LOG] {msg}", flush=True)

# =========================
# HOME UI
# =========================
@app.route("/")
def index():
    return """
<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>Photo Server</title>

<style>
body { font-family: sans-serif; padding: 20px; }

#log {
    margin-top: 15px;
    padding: 10px;
    background: #000;
    color: #00ff00;
    height: 320px;
    overflow-y: auto;
    font-family: monospace;
    font-size: 12px;
    border-radius: 6px;
}

button { margin: 5px; padding: 8px 12px; }

#status { margin-top: 10px; color: gray; }
</style>
</head>

<body>

<h1>📷 Photo Upload Server</h1>

<input type="file" id="file" multiple />
<br>

<button onclick="upload()">Upload</button>
<button onclick="shutdown()">Stop Server</button>
<button onclick="toggleAuto()">Auto Log: OFF</button>

<div id="status">Status: running</div>
<div id="log"></div>

<script>

let auto = false;
let timer = null;

function log(msg){
    const el = document.getElementById("log");
    el.innerHTML += msg + "<br>";
    el.scrollTop = el.scrollHeight;
}

async function upload(){
    const files = document.getElementById('file').files;

    if(!files.length){
        log("⚠ No files");
        return;
    }

    for(let f of files){
        log("⬆ " + f.name);

        const fd = new FormData();
        fd.append("image", f);

        try {
            const r = await fetch("/upload", {
                method: "POST",
                body: fd
            });

            const j = await r.json();
            log("✔ " + f.name + " => " + JSON.stringify(j));

        } catch(e){
            log("❌ " + e);
        }
    }
}

async function shutdown(){
    log("🛑 shutting down...");

    try {
        const r = await fetch("/shutdown", { method: "POST" });
        const j = await r.json();
        log("✔ " + JSON.stringify(j));
        document.getElementById("status").innerText = "Status: stopped";
    } catch(e){
        log("❌ shutdown error " + e);
    }
}

function toggleAuto(){
    auto = !auto;

    const btn = document.getElementsByTagName("button")[2];

    if(auto){
        btn.innerText = "Auto Log: ON";

        timer = setInterval(async () => {
            try {
                const r = await fetch("/logs");
                const j = await r.json();
                log("[AUTO] " + JSON.stringify(j));
            } catch(e){
                log("[AUTO ERROR] " + e);
            }
        }, 2000);

    } else {
        btn.innerText = "Auto Log: OFF";
        clearInterval(timer);
    }
}

</script>

</body>
</html>
"""

# =========================
# UPLOAD
# =========================
@app.route("/upload", methods=["POST"])
def upload():
    try:
        file = request.files.get("image")
        if not file:
            return jsonify({"error": "no file"}), 400

        data = file.read()
        sha = hashlib.sha256(data).hexdigest()

        ext = os.path.splitext(file.filename)[1].lower()
        if ext not in [".jpg", ".jpeg", ".png", ".webp", ".gif"]:
            return jsonify({"error": "bad ext"}), 400

        dt = datetime.datetime.now(datetime.timezone.utc)
        year = str(dt.year)

        photo_path = PHOTO_DIR / year / f"{sha}{ext}"
        thumb_path = THUMB_DIR / year / f"{sha}{ext}"

        photo_path.parent.mkdir(parents=True, exist_ok=True)
        thumb_path.parent.mkdir(parents=True, exist_ok=True)

        log(f"PHOTO {photo_path}")

        with open(photo_path, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())

        try:
            img = Image.open(io.BytesIO(data))
            img.thumbnail((400, 400))
            if img.mode in ("RGBA", "LA", "P"):
                img = img.convert("RGB")
            img.save(thumb_path)
        except Exception as e:
            log(f"thumb error {e}")
            shutil.copy(photo_path, thumb_path)

        photos_db[sha] = {
            "name": file.filename,
            "path": str(photo_path.relative_to(BASE_DIR)),
            "thumb": str(thumb_path.relative_to(BASE_DIR)),
            "time": dt.isoformat()
        }

        tmp = JSON_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(photos_db, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(JSON_FILE)

        return jsonify({"ok": True, "sha": sha})

    except Exception as e:
        log("ERROR")
        log(str(e))
        log(traceback.format_exc())
        return jsonify({"error": str(e)}), 500

# =========================
# LOGS API
# =========================
@app.route("/logs")
def logs():
    return jsonify({
        "status": "running",
        "time": datetime.datetime.utcnow().isoformat()
    })

# =========================
# SHUTDOWN (FIXED)
# =========================
import threading
import time

@app.route("/shutdown", methods=["POST"])
def shutdown():
    log("SHUTDOWN TRIGGERED")

    def killer():
        time.sleep(0.3)  # 给 HTTP response 时间返回
        log("KILL PROCESS NOW")
        os._exit(0)

    threading.Thread(target=killer).start()

    return jsonify({"ok": True})
# =========================
# MAIN
# =========================
if __name__ == "__main__":
    log(f"BASE {BASE_DIR}")
    app.run(host="0.0.0.0", port=5000, debug=False)