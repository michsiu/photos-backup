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

ALLOWED_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".gif", ".webp"
}

# =========================
# LOG
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
# DB
# =========================

if JSON_FILE.exists():
    try:
        photos_db = json.loads(
            JSON_FILE.read_text(encoding="utf-8")
        )
    except:
        photos_db = {}
else:
    photos_db = {}

# =========================
# HTML
# =========================

UPLOAD_PAGE = """
<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>Uploader</title>

<style>
body{
    font-family:sans-serif;
    max-width:900px;
    margin:30px auto;
}

button{
    padding:10px 15px;
    margin-right:10px;
}

#logs{
    background:#111;
    color:#0f0;
    height:300px;
    overflow:auto;
    padding:10px;
    white-space:pre-wrap;
}
</style>
</head>

<body>

<h2>Photo Upload</h2>

<input type="file" id="file" multiple>

<br><br>

<button onclick="upload()">Upload</button>
<button onclick="toggleLogs()">Pause Logs</button>
<button onclick="stopServer()">Stop Server</button>

<pre id="logs"></pre>

<script>

let timer = null;
let logsEnabled = true;
let lastLogLength = 0;

// =========================
// upload
// =========================

async function upload(){

    const files = document.getElementById('file').files;

    for(const file of files){

        const fd = new FormData();

        fd.append('image', file);

        await fetch('/upload',{
            method:'POST',
            body:fd
        });
    }
}

// =========================
// logs
// =========================

async function fetchLogs(){

    try{

        const r = await fetch('/logs');

        const t = await r.text();

        const el = document.getElementById('logs');

        el.textContent = t;

        el.scrollTop = el.scrollHeight;

    }catch(e){
        console.log(e);
    }
}

function startLogs(){

    if(timer) return;

    timer = setInterval(fetchLogs,1000);
}

function stopLogs(){

    clearInterval(timer);

    timer = null;
}

function toggleLogs(){

    logsEnabled = !logsEnabled;

    if(logsEnabled){

        startLogs();

    }else{

        stopLogs();
    }
}

// =========================
// shutdown
// =========================

async function stopServer(){

    const ok = confirm("Stop server?");

    if(!ok) return;

    try{

        await fetch('/shutdown',{
            method:'POST'
        });

        alert("Server stopped");

    }catch(e){

        console.log(e);
    }
}

startLogs();

</script>

</body>
</html>
"""

# =========================
# ROUTES
# =========================

@app.route("/")
def index():
    return UPLOAD_PAGE

@app.route("/logs")
def logs():
    return "\n".join(log_buffer)

# =========================
# EXIF
# =========================

def get_exif_date(data):

    try:

        exif = piexif.load(data)

        for ifd in ["Exif","0th"]:

            for tag in [36867,36868,306]:

                if tag in exif.get(ifd,{}):

                    dt = exif[ifd][tag].decode()

                    return datetime.datetime.strptime(
                        dt,
                        "%Y:%m:%d %H:%M:%S"
                    )

    except:

        print(traceback.format_exc())

    return None

# =========================
# UPLOAD
# =========================

@app.route("/upload",methods=["POST"])
def upload():

    try:

        if "image" not in request.files:
            return jsonify({"error":"no file"}),400

        file = request.files["image"]

        log(f"UPLOAD {file.filename}")

        data = file.read()

        sha = hashlib.sha256(data).hexdigest()

        ext = os.path.splitext(file.filename)[1].lower()

        if ext not in ALLOWED_EXTENSIONS:
            return jsonify({"error":"bad ext"}),400

        dt = get_exif_date(data)

        if not dt:
            dt = datetime.datetime.utcnow()

        year = str(dt.year)

        photo_path = Path(f"photos/{year}/{sha}{ext}")
        thumb_path = Path(f"thumbs/{year}/{sha}{ext}")

        photo_path.parent.mkdir(
            parents=True,
            exist_ok=True
        )

        thumb_path.parent.mkdir(
            parents=True,
            exist_ok=True
        )

        with open(photo_path,"wb") as f:
            f.write(data)

        try:

            img = Image.open(io.BytesIO(data))

            img.thumbnail((400,400))

            img.save(thumb_path)

        except:

            shutil.copy(photo_path,thumb_path)

        photos_db[sha] = {
            "file":file.filename,
            "path":str(photo_path)
        }

        JSON_FILE.write_text(
            json.dumps(
                photos_db,
                indent=2,
                ensure_ascii=False
            ),
            encoding="utf-8"
        )

        log("DONE")

        return jsonify({"ok":True})

    except Exception as e:

        print(traceback.format_exc())

        return jsonify({"error":str(e)}),500

# =========================
# SHUTDOWN
# =========================

@app.route("/shutdown",methods=["POST"])
def shutdown():

    log("SERVER STOP REQUEST")

    # 给 workflow 发退出信号
    Path("STOP").touch()

    return jsonify({"ok":True})

# =========================
# MAIN
# =========================

if __name__ == "__main__":

    log("SERVER START")

    app.run(
        host="0.0.0.0",
        port=5000,
        debug=False
    )