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
# 🔥 FIX: 永远锁 repo root
# =========================
BASE_DIR = Path(__file__).resolve().parent

UPLOAD_FOLDER = BASE_DIR / "photos"
THUMB_FOLDER = BASE_DIR / "thumbs"
JSON_FILE = BASE_DIR / "photos.json"

UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)
THUMB_FOLDER.mkdir(parents=True, exist_ok=True)

# =========================
# 内存数据库
# =========================
if JSON_FILE.exists():
    photos_db = json.loads(JSON_FILE.read_text(encoding="utf-8"))
else:
    photos_db = {}

# =========================
# 简单日志
# =========================
def log(msg):
    print(f"[LOG] {msg}", flush=True)

# =========================
# EXIF 时间
# =========================
def get_exif_date(image_bytes):
    try:
        exif_dict = piexif.load(image_bytes)
        for ifd_name in ["Exif", "0th"]:
            ifd = exif_dict.get(ifd_name, {})
            for tag in [36867, 36868, 306]:
                if tag in ifd:
                    dt_str = ifd[tag].decode(errors="ignore")
                    dt = datetime.datetime.strptime(dt_str, "%Y:%m:%d %H:%M:%S")
                    return dt.replace(tzinfo=datetime.timezone.utc)
    except Exception as e:
        log(f"EXIF ERROR: {e}")
    return None

# =========================
# 时间兜底
# =========================
def get_utc_now():
    return datetime.datetime.now(datetime.timezone.utc)

# =========================
# 上传接口
# =========================
@app.route("/upload", methods=["POST"])
def upload():
    try:
        log("🔥 UPLOAD HIT")

        file = request.files.get("image")
        if not file:
            return jsonify({"error": "no file"}), 400

        image_bytes = file.read()

        sha256 = hashlib.sha256(image_bytes).hexdigest()
        ext = os.path.splitext(file.filename)[1].lower()

        if ext not in [".jpg", ".jpeg", ".png", ".gif", ".webp"]:
            return jsonify({"error": "bad ext"}), 400

        # 时间
        dt = get_exif_date(image_bytes) or get_utc_now()
        year = str(dt.year)

        # =========================
        # 🔥 FIX: 绝对路径写入
        # =========================
        photo_path = UPLOAD_FOLDER / year / f"{sha256}{ext}"
        thumb_path = THUMB_FOLDER / year / f"{sha256}{ext}"

        photo_path.parent.mkdir(parents=True, exist_ok=True)
        thumb_path.parent.mkdir(parents=True, exist_ok=True)

        log(f"CWD = {os.getcwd()}")
        log(f"PHOTO_PATH = {photo_path}")
        log(f"THUMB_PATH = {thumb_path}")
        log(f"JSON_PATH = {JSON_FILE}")

        # =========================
        # 写原图
        # =========================
        with open(photo_path, "wb") as f:
            f.write(image_bytes)
            f.flush()
            os.fsync(f.fileno())

        # =========================
        # 缩略图
        # =========================
        try:
            img = Image.open(io.BytesIO(image_bytes))
            img.thumbnail((400, 400))

            if img.mode in ("RGBA", "LA", "P"):
                img = img.convert("RGB")

            img.save(thumb_path)
        except Exception as e:
            log(f"THUMB ERROR: {e}")
            shutil.copy(photo_path, thumb_path)

        # =========================
        # JSON 更新
        # =========================
        photos_db[sha256] = {
            "fileName": file.filename,
            "path": str(photo_path.relative_to(BASE_DIR)),
            "thumb": str(thumb_path.relative_to(BASE_DIR)),
            "year": year,
            "sha256": sha256,
            "time": dt.isoformat()
        }

        # =========================
        # 🔥 atomic write
        # =========================
        tmp = JSON_FILE.with_suffix(".tmp")

        tmp.write_text(
            json.dumps(photos_db, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )
        tmp.replace(JSON_FILE)

        log("✅ SAVED OK")

        return jsonify({
            "status": "ok",
            "sha256": sha256,
            "path": str(photo_path)
        })

    except Exception as e:
        log("❌ UPLOAD ERROR")
        log(str(e))
        log(traceback.format_exc())
        return jsonify({"error": str(e)}), 500

# =========================
# shutdown
# =========================
@app.route("/shutdown", methods=["POST"])
def shutdown():
    log("🛑 shutdown called")
    func = request.environ.get("werkzeug.server.shutdown")
    if func:
        func()
    return jsonify({"ok": True})

# =========================
# main
# =========================
if __name__ == "__main__":
    log(f"BASE_DIR = {BASE_DIR}")
    app.run(host="0.0.0.0", port=5000, debug=False)