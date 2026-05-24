import os
import io
import json
import hashlib
import datetime
import shutil
import re
import traceback
import threading
import time
from pathlib import Path
from flask import Flask, request, jsonify
from PIL import Image
import piexif

app = Flask(__name__)

# =========================
# PATH SETUP
# =========================
BASE_DIR = Path(__file__).resolve().parent

PHOTO_DIR = BASE_DIR / "photos"
THUMB_DIR = BASE_DIR / "thumbs"
JSON_FILE = BASE_DIR / "photos.json"

PHOTO_DIR.mkdir(parents=True, exist_ok=True)
THUMB_DIR.mkdir(parents=True, exist_ok=True)

ALLOWED_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.tiff'}

# =========================
# DATABASE
# =========================
if JSON_FILE.exists():
    try:
        photos_db = json.loads(JSON_FILE.read_text(encoding="utf-8"))
    except Exception:
        photos_db = {}
else:
    photos_db = {}

def log(msg):
    print(f"[LOG] {msg}", flush=True)

# =========================
# DATE PARSING (EXIF first, then ==boundary==, fallback UTC)
# =========================
def get_exif_datetime(image_bytes: bytes) -> datetime.datetime | None:
    """Extract datetime from EXIF, return timezone-aware datetime or None."""
    try:
        exif_dict = piexif.load(image_bytes)
        for ifd_name in ("Exif", "0th"):
            ifd = exif_dict.get(ifd_name, {})
            # Look for DateTimeOriginal (36867), DateTimeDigitized (36868), DateTime (306)
            for tag in (36867, 36868, 306):
                if tag in ifd:
                    dt_str = ifd[tag].decode("utf-8", errors="ignore")
                    # Format: "YYYY:MM:DD HH:MM:SS"
                    naive = datetime.datetime.strptime(dt_str, "%Y:%m:%d %H:%M:%S")
                    # Try to find timezone offset (OffsetTimeOriginal 0x9010, etc.)
                    offset_tag = None
                    if ifd_name == "Exif":
                        offset_tag = ifd.get(0x9010) or ifd.get(0x9011)
                    if offset_tag:
                        offset_str = offset_tag.decode("utf-8", errors="ignore")
                        # Format "+08:00" or "+0800"
                        if ":" in offset_str:
                            h, m = map(int, offset_str.split(":"))
                        else:
                            h = int(offset_str[:3])
                            m = int(offset_str[3:5]) if len(offset_str) > 3 else 0
                        tz = datetime.timezone(datetime.timedelta(hours=h, minutes=m))
                        return naive.replace(tzinfo=tz)
                    # No timezone info => return None (we won't guess)
                    return None
        return None
    except Exception:
        return None

def parse_date_from_boundary(filename: str) -> datetime.datetime | None:
    """Parse date from 'ISO-DATE==boundary==realname.jpg' pattern. Date must have timezone offset."""
    if "==boundary==" not in filename:
        return None
    date_part = filename.split("==boundary==", 1)[0].strip()
    # Try common ISO formats with timezone
    for fmt in [
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S%Z",
        "%Y-%m-%d %H:%M:%S%z",
        "%Y-%m-%dT%H:%M%z",
        "%Y-%m-%d %H:%M%z",
    ]:
        try:
            return datetime.datetime.strptime(date_part, fmt)
        except ValueError:
            continue
    # Try parsing without timezone and assume Beijing time (+08:00)
    for fmt in ["%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M"]:
        try:
            naive = datetime.datetime.strptime(date_part, fmt)
            bj_tz = datetime.timezone(datetime.timedelta(hours=8))
            return naive.replace(tzinfo=bj_tz)
        except ValueError:
            continue
    return None

def get_utc_datetime(image_bytes: bytes, original_filename: str) -> datetime.datetime:
    """
    Returns a timezone-aware UTC datetime for the photo.
    Priority: EXIF -> boundary in filename -> current UTC.
    """
    dt = get_exif_datetime(image_bytes)
    if dt:
        return dt.astimezone(datetime.timezone.utc)
    dt = parse_date_from_boundary(original_filename)
    if dt:
        return dt.astimezone(datetime.timezone.utc)
    return datetime.datetime.now(datetime.timezone.utc)

def get_real_filename(raw_name: str) -> str:
    """Extract real filename after ==boundary== if present."""
    if "==boundary==" in raw_name:
        return raw_name.split("==boundary==", 1)[1].strip()
    return raw_name

# =========================
# FRONTEND (modern & clean)
# =========================
@app.route("/")
def index():
    return """
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Photo Upload</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
         background: #f0f2f5; color: #1a1a2e; padding: 40px 20px; max-width: 680px; margin: 0 auto; }
  h1 { font-size: 2rem; margin-bottom: 24px; display: flex; align-items: center; gap: 8px; }
  .card { background: white; border-radius: 20px; padding: 28px; box-shadow: 0 8px 24px rgba(0,0,0,0.06); margin-bottom: 24px; }
  input[type=file] { width: 100%; padding: 14px; border: 2px dashed #d1d5db; border-radius: 12px; cursor: pointer; background: #f9fafb; }
  .btn-group { display: flex; gap: 12px; margin-top: 18px; flex-wrap: wrap; }
  button { padding: 10px 22px; border: none; border-radius: 10px; font-weight: 600; cursor: pointer; transition: all 0.2s; font-size: 0.95rem; }
  .btn-upload { background: #4f46e5; color: white; }
  .btn-stop { background: #ef4444; color: white; }
  .btn-auto { background: #e5e7eb; color: #1f2937; }
  button:hover { transform: translateY(-1px); box-shadow: 0 4px 12px rgba(0,0,0,0.1); }
  #logBox { margin-top: 16px; background: #0f172a; color: #a7f3d0; padding: 16px; border-radius: 12px;
            height: 280px; overflow-y: auto; font-family: 'JetBrains Mono', Consolas, monospace; font-size: 0.85rem; line-height: 1.6; }
  .status { margin-top: 10px; font-size: 0.9rem; color: #6b7280; }
  a { color: #4f46e5; }
</style>
</head>
<body>
  <h1>📷 Photo Upload</h1>
  <div class="card">
    <input type="file" id="fileInput" multiple accept="image/*" />
    <div class="btn-group">
      <button class="btn-upload" onclick="uploadFiles()">⬆ Upload All</button>
      <button class="btn-stop" onclick="shutdownServer()">⏹ Stop & Commit</button>
      <button class="btn-auto" onclick="toggleAuto()" id="autoBtn">Auto Log: OFF</button>
    </div>
    <div class="status" id="status">Ready</div>
    <pre id="logBox"></pre>
  </div>
  <script>
    let auto = false, timer;
    function log(msg) {
      const box = document.getElementById('logBox');
      box.textContent += msg + '\\n';
      box.scrollTop = box.scrollHeight;
    }
    async function uploadFiles() {
      const files = document.getElementById('fileInput').files;
      if (!files.length) { log('⚠ No files selected'); return; }
      for (const f of files) {
        log('⬆ ' + f.name);
        const fd = new FormData();
        fd.append('image', f);
        try {
          const resp = await fetch('/upload', { method: 'POST', body: fd });
          const json = await resp.json();
          if (json.ok) {
            log('✔ ' + f.name + '  →  ' + json.sha.substring(0,8));
          } else {
            log('❌ ' + f.name + '  error: ' + (json.error || 'unknown'));
          }
        } catch (e) {
          log('❌ ' + f.name + '  network error: ' + e);
        }
      }
      log('✅ Batch finished');
    }
    async function shutdownServer() {
      log('🛑 Sending shutdown...');
      try {
        const resp = await fetch('/shutdown', { method: 'POST' });
        const json = await resp.json();
        log('✔ Server stopped: ' + JSON.stringify(json));
        document.getElementById('status').innerText = 'Server stopped – changes will be committed';
      } catch (e) {
        log('❌ Shutdown error: ' + e);
      }
    }
    function toggleAuto() {
      auto = !auto;
      const btn = document.getElementById('autoBtn');
      if (auto) {
        btn.innerText = 'Auto Log: ON';
        timer = setInterval(async () => {
          try {
            const r = await fetch('/logs');
            const j = await r.json();
            log('[AUTO] ' + JSON.stringify(j));
          } catch (e) { log('[AUTO ERR] ' + e); }
        }, 3000);
      } else {
        btn.innerText = 'Auto Log: OFF';
        clearInterval(timer);
      }
    }
  </script>
</body>
</html>
"""

# =========================
# UPLOAD HANDLER
# =========================
@app.route("/upload", methods=["POST"])
def upload():
    try:
        file = request.files.get("image")
        if not file:
            return jsonify({"ok": False, "error": "no file"}), 400

        data = file.read()
        sha = hashlib.sha256(data).hexdigest()
        ext = os.path.splitext(file.filename)[1].lower()
        if ext not in ALLOWED_EXTENSIONS:
            return jsonify({"ok": False, "error": f"unsupported extension {ext}"}), 400

        # Determine timestamp and year (UTC)
        dt_utc = get_utc_datetime(data, file.filename)
        year = str(dt_utc.year)
        date_iso = dt_utc.strftime("%Y-%m-%dT%H:%M:%SZ")

        # Prepare paths
        photo_rel = f"photos/{year}/{sha}{ext}"
        thumb_rel = f"thumbs/{year}/{sha}{ext}"
        photo_path = BASE_DIR / photo_rel
        thumb_path = BASE_DIR / thumb_rel
        photo_path.parent.mkdir(parents=True, exist_ok=True)
        thumb_path.parent.mkdir(parents=True, exist_ok=True)

        # Save original
        with open(photo_path, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())

        # Generate thumbnail
        try:
            img = Image.open(io.BytesIO(data))
            img.thumbnail((400, 400))
            # Handle transparency
            if img.mode in ("RGBA", "LA", "P"):
                img = img.convert("RGB")
            img.save(thumb_path)
        except Exception as e:
            log(f"Thumbnail generation failed: {e}")
            shutil.copyfile(photo_path, thumb_path)

        # Update database
        real_name = get_real_filename(file.filename)
        photos_db[sha] = {
            "fileName": real_name,
            "url": photo_rel,          # relative path
            "thumbnail": thumb_rel,    # relative path
            "year": year,
            "date": date_iso,
            "sha256": sha
        }

        # Atomic write to JSON
        tmp_json = JSON_FILE.with_suffix(".tmp")
        tmp_json.write_text(json.dumps(photos_db, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp_json.replace(JSON_FILE)

        log(f"Stored {sha[:8]} -> {photo_rel}")
        return jsonify({"ok": True, "sha": sha})

    except Exception as e:
        log("UPLOAD ERROR")
        log(str(e))
        log(traceback.format_exc())
        return jsonify({"ok": False, "error": str(e)}), 500

# =========================
# LOGS API (for auto log)
# =========================
@app.route("/logs")
def logs():
    return jsonify({
        "status": "running",
        "time": datetime.datetime.utcnow().isoformat()
    })

# =========================
# GRACEFUL SHUTDOWN
# =========================
@app.route("/shutdown", methods=["POST"])
def shutdown():
    log("SHUTDOWN TRIGGERED – final save...")
    # Final flush of photos.json
    try:
        JSON_FILE.write_text(json.dumps(photos_db, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception as e:
        log(f"Final write error: {e}")

    def killer():
        time.sleep(0.5)
        os._exit(0)

    threading.Thread(target=killer).start()
    return jsonify({"ok": True, "message": "shutting down"})

# =========================
# MAIN
# =========================
if __name__ == "__main__":
    log(f"Working directory: {BASE_DIR}")
    app.run(host="0.0.0.0", port=5000, debug=False)