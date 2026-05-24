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

app = Flask(__name__)

# =========================
# 🔥 锁 repo root（关键修复）
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
# 时间
# =========================
def now_utc():
    return datetime.datetime.now(datetime.timezone.utc)

# =========================
# upload
# =========================
@app.route("/upload", methods=["POST"])
def upload():
    try:
        log("UPLOAD HIT")

        file = request.files.get("image")
        if not file:
            return jsonify({"error": "no file"}), 400

        data = file.read()
        sha = hashlib.sha256(data).hexdigest()

        ext = os.path.splitext(file.filename)[1].lower()
        if ext not in [".jpg", ".jpeg", ".png", ".webp", ".gif"]:
            return jsonify({"error": "bad ext"}), 400

        dt = now_utc()
        year = str(dt.year)

        photo_path = PHOTO_DIR / year / f"{sha}{ext}"
        thumb_path = THUMB_DIR / year / f"{sha}{ext}"

        photo_path.parent.mkdir(parents=True, exist_ok=True)
        thumb_path.parent.mkdir(parents=True, exist_ok=True)

        log(f"PHOTO = {photo_path}")
        log(f"JSON  = {JSON_FILE}")

        # 写原图
        with open(photo_path, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())

        # 缩略图
        try:
            img = Image.open(io.BytesIO(data))
            img.thumbnail((400, 400))
            if img.mode in ("RGBA", "LA", "P"):
                img = img.convert("RGB")
            img.save(thumb_path)
        except Exception as e:
            log(f"thumb fail: {e}")
            shutil.copy(photo_path, thumb_path)

        # 更新 JSON
        photos_db[sha] = {
            "name": file.filename,
            "path": str(photo_path.relative_to(BASE_DIR)),
            "thumb": str(thumb_path.relative_to(BASE_DIR)),
            "time": dt.isoformat()
        }

        tmp = JSON_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(photos_db, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(JSON_FILE)

        log("SAVE OK")

        return jsonify({"ok": True, "sha": sha})

    except Exception as e:
        log("UPLOAD ERROR")
        log(str(e))
        log(traceback.format_exc())
        return jsonify({"error": str(e)}), 500

# =========================
# shutdown
# =========================
@app.route("/shutdown", methods=["POST"])
def shutdown():
    log("SHUTDOWN CALLED")
    func = request.environ.get("werkzeug.server.shutdown")
    if func:
        func()
    return jsonify({"ok": True})

# =========================
# main
# =========================
if __name__ == "__main__":
    log(f"BASE = {BASE_DIR}")
    app.run(host="0.0.0.0", port=5000, debug=False)