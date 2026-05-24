import os
import io
import json
import hashlib
import datetime
import shutil
import traceback
import logging
import sys

from pathlib import Path
from logging.handlers import RotatingFileHandler

from flask import Flask, request, jsonify
from PIL import Image
import piexif

# =========================================================
# Flask
# =========================================================

app = Flask(__name__)

# =========================================================
# Paths
# =========================================================

UPLOAD_FOLDER = Path('photos')
THUMB_FOLDER = Path('thumbs')
JSON_FILE = Path('photos.json')
LOG_FILE = Path('server.log')

ALLOWED_EXTENSIONS = {
    '.jpg',
    '.jpeg',
    '.png',
    '.gif',
    '.webp',
    '.bmp',
    '.tiff'
}

# =========================================================
# Logging
# =========================================================

logger = logging.getLogger('photo_server')
logger.setLevel(logging.INFO)

formatter = logging.Formatter(
    '[%(asctime)s] %(levelname)s | %(message)s',
    datefmt='%H:%M:%S'
)

# 控制台日志（GitHub Actions 可实时输出）
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(formatter)

# 文件日志
file_handler = RotatingFileHandler(
    LOG_FILE,
    maxBytes=5 * 1024 * 1024,
    backupCount=3,
    encoding='utf-8'
)
file_handler.setFormatter(formatter)

logger.addHandler(console_handler)
logger.addHandler(file_handler)

# =========================================================
# Database
# =========================================================

if JSON_FILE.exists():
    try:
        with open(JSON_FILE, 'r', encoding='utf-8') as f:
            photos_db = json.load(f)
    except Exception:
        logger.error('Failed to load photos.json')
        logger.error(traceback.format_exc())
        photos_db = {}
else:
    photos_db = {}

# =========================================================
# HTML
# =========================================================

UPLOAD_PAGE = '''
<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>照片上传器</title>

<style>
body {
    font-family: sans-serif;
    max-width: 800px;
    margin: 30px auto;
    padding: 20px;
    background: #f5f5f5;
}

h1 {
    margin-bottom: 20px;
}

button {
    padding: 12px 20px;
    border: none;
    background: black;
    color: white;
    border-radius: 10px;
    cursor: pointer;
    margin-top: 10px;
}

button:hover {
    opacity: 0.85;
}

#progress {
    margin-top: 20px;
}

#logs {
    margin-top: 20px;
    background: #111;
    color: #0f0;
    padding: 12px;
    height: 300px;
    overflow-y: auto;
    white-space: pre-wrap;
    border-radius: 10px;
    font-size: 12px;
}
</style>
</head>

<body>

<h1>📷 批量上传照片</h1>

<input type="file" id="fileInput" multiple accept="image/*">

<br>

<button onclick="uploadFiles()">开始上传</button>

<button onclick="shutdown()">关闭服务</button>

<div id="progress"></div>

<pre id="logs"></pre>

<script>

async function uploadFiles() {

    const files = document.getElementById('fileInput').files;

    if (!files.length) {
        alert('请选择文件');
        return;
    }

    const progressDiv = document.getElementById('progress');

    progressDiv.innerHTML = '';

    let count = 0;

    for (const [index, file] of [...files].entries()) {

        const line = document.createElement('div');
        line.textContent = `[${index + 1}/${files.length}] 上传中: ${file.name}`;
        progressDiv.appendChild(line);

        const formData = new FormData();
        formData.append('image', file);

        try {

            const resp = await fetch('/upload', {
                method: 'POST',
                body: formData
            });

            const result = await resp.json();

            line.textContent =
                `[${index + 1}/${files.length}] ${file.name} → ${result.status} (${result.sha256?.slice(0, 8) || 'ERR'})`;

            count++;

        } catch (err) {

            line.textContent =
                `[${index + 1}/${files.length}] ${file.name} → 失败: ${err}`;
        }
    }

    alert(`上传完成，共处理 ${count} 个文件`);
}

async function shutdown() {

    await fetch('/shutdown', {
        method: 'POST'
    });

    alert('服务已关闭');
}

async function pollLogs() {

    try {

        const resp = await fetch('/logs');

        const text = await resp.text();

        const el = document.getElementById('logs');

        el.textContent = text;

        el.scrollTop = el.scrollHeight;

    } catch (e) {}
}

setInterval(pollLogs, 1000);

</script>

</body>
</html>
'''

# =========================================================
# Flask Logs
# =========================================================

@app.before_request
def log_request():
    logger.info(f'{request.method} {request.path} from {request.remote_addr}')

# =========================================================
# Routes
# =========================================================

@app.route('/')
def index():
    return UPLOAD_PAGE

@app.route('/logs')
def logs():

    try:

        if not LOG_FILE.exists():
            return ''

        return LOG_FILE.read_text(encoding='utf-8')

    except Exception:
        logger.error(traceback.format_exc())
        return 'log read failed'

# =========================================================
# EXIF
# =========================================================

def get_exif_date(image_bytes: bytes):

    try:

        exif_dict = piexif.load(image_bytes)

        for ifd_name in ['Exif', '0th']:

            ifd = exif_dict.get(ifd_name, {})

            for tag_id in [36867, 36868, 306]:

                if tag_id in ifd:

                    dt_str = ifd[tag_id].decode(
                        'utf-8',
                        errors='ignore'
                    )

                    naive_dt = datetime.datetime.strptime(
                        dt_str,
                        '%Y:%m:%d %H:%M:%S'
                    )

                    offset_tag = None

                    if ifd_name == 'Exif':
                        offset_tag = (
                            ifd.get(0x9010)
                            or ifd.get(0x9011)
                        )

                    if offset_tag:

                        offset_str = offset_tag.decode(
                            'utf-8',
                            errors='ignore'
                        )

                        sign = 1

                        if offset_str.startswith('-'):
                            sign = -1

                        offset_str = offset_str.replace('+', '').replace('-', '')

                        hours, minutes = map(
                            int,
                            offset_str.split(':')
                        )

                        delta = datetime.timedelta(
                            hours=hours * sign,
                            minutes=minutes * sign
                        )

                        tz = datetime.timezone(delta)

                        logger.info('Date source: EXIF')

                        return naive_dt.replace(tzinfo=tz)

                    logger.warning('EXIF exists but no timezone')

    except Exception:
        logger.error('EXIF parse failed')
        logger.error(traceback.format_exc())

    return None

# =========================================================
# Filename Parse
# =========================================================

def parse_date_from_filename(filename: str):

    try:

        if '==boundary==' not in filename:
            return None

        date_part, _ = filename.split('==boundary==', 1)

        date_part = date_part.strip()

        try:

            dt = datetime.datetime.fromisoformat(date_part)

            logger.info('Date source: filename')

            return dt

        except Exception:
            pass

        formats = [
            '%Y-%m-%dT%H:%M:%S%z',
            '%Y-%m-%dT%H:%M%z',
            '%Y-%m-%dT%H:%M:%S',
            '%Y-%m-%d %H:%M:%S%z'
        ]

        for fmt in formats:

            try:

                if fmt.endswith('%z'):

                    dt = datetime.datetime.strptime(date_part, fmt)

                    logger.info('Date source: filename')

                    return dt

                else:

                    dt_naive = datetime.datetime.strptime(date_part, fmt)

                    dt_bj = dt_naive.replace(
                        tzinfo=datetime.timezone(
                            datetime.timedelta(hours=8)
                        )
                    )

                    logger.info('Date source: filename')

                    return dt_bj

            except Exception:
                continue

    except Exception:
        logger.error(traceback.format_exc())

    return None

# =========================================================
# Datetime
# =========================================================

def get_utc_datetime(image_bytes: bytes, filename: str):

    dt = get_exif_date(image_bytes)

    if dt is not None:
        return dt.astimezone(datetime.timezone.utc)

    dt = parse_date_from_filename(filename)

    if dt is not None:
        return dt.astimezone(datetime.timezone.utc)

    logger.warning('Date source: fallback_now')

    return datetime.datetime.now(datetime.timezone.utc)

# =========================================================
# Filename
# =========================================================

def get_original_filename(filename: str):

    if '==boundary==' in filename:

        _, real_name = filename.split('==boundary==', 1)

        return real_name.strip()

    return filename

# =========================================================
# Upload
# =========================================================

@app.route('/upload', methods=['POST'])
def upload():

    start_time = datetime.datetime.now()

    try:

        if 'image' not in request.files:
            return jsonify({
                'status': 'error',
                'message': '没有文件'
            }), 400

        file = request.files['image']

        if file.filename == '':
            return jsonify({
                'status': 'error',
                'message': '空文件名'
            }), 400

        logger.info(f'Upload start: {file.filename}')

        image_bytes = file.read()

        size_mb = len(image_bytes) / 1024 / 1024

        logger.info(f'File size: {size_mb:.2f} MB')

        sha256 = hashlib.sha256(image_bytes).hexdigest()

        logger.info(f'SHA256: {sha256}')

        original_name = get_original_filename(file.filename)

        ext = os.path.splitext(original_name)[1].lower()

        if ext not in ALLOWED_EXTENSIONS:

            logger.warning(f'Unsupported extension: {ext}')

            return jsonify({
                'status': 'error',
                'message': f'不支持的文件类型 {ext}'
            }), 400

        utc_dt = get_utc_datetime(
            image_bytes,
            file.filename
        )

        logger.info(f'UTC datetime: {utc_dt.isoformat()}')

        year = str(utc_dt.year)

        date_str = utc_dt.strftime('%Y-%m-%dT%H:%M:%SZ')

        photo_rel = f'photos/{year}/{sha256}{ext}'
        thumb_rel = f'thumbs/{year}/{sha256}{ext}'

        photo_abs = Path(photo_rel)
        thumb_abs = Path(thumb_rel)

        photo_abs.parent.mkdir(
            parents=True,
            exist_ok=True
        )

        thumb_abs.parent.mkdir(
            parents=True,
            exist_ok=True
        )

        logger.info(f'Saving original -> {photo_abs}')

        with open(photo_abs, 'wb') as f:
            f.write(image_bytes)

        try:

            logger.info(f'Generating thumbnail -> {thumb_abs}')

            img = Image.open(io.BytesIO(image_bytes))

            img.thumbnail((400, 400))

            if img.mode in ('RGBA', 'LA') or (
                img.mode == 'P'
                and 'transparency' in img.info
            ):
                img = img.convert('RGB')

            img.save(thumb_abs)

        except Exception as e:

            logger.error(f'Thumbnail failed: {e}')
            logger.error(traceback.format_exc())

            shutil.copy(photo_abs, thumb_abs)

        photos_db[sha256] = {
            'fileName': original_name,
            'url': photo_rel,
            'thumbnail': thumb_rel,
            'year': year,
            'date': date_str,
            'sha256': sha256
        }

        logger.info(f'Updating {JSON_FILE}')

        with open(JSON_FILE, 'w', encoding='utf-8') as f:
            json.dump(
                photos_db,
                f,
                indent=2,
                ensure_ascii=False
            )

        elapsed = (
            datetime.datetime.now() - start_time
        ).total_seconds()

        logger.info(f'Upload success: {original_name}')
        logger.info(f'Finished in {elapsed:.2f}s')

        return jsonify({
            'status': 'ok',
            'sha256': sha256,
            'url': photo_rel
        })

    except Exception as e:

        logger.error(f'Upload failed: {e}')
        logger.error(traceback.format_exc())

        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

# =========================================================
# Shutdown
# =========================================================

@app.route('/shutdown', methods=['POST'])
def shutdown():

    logger.warning('Shutdown requested')

    func = request.environ.get('werkzeug.server.shutdown')

    if func is None:

        logger.warning('Using os._exit(0)')

        os._exit(0)

    func()

    return 'Server shutting down...'

# =========================================================
# Main
# =========================================================

if __name__ == '__main__':

    logger.info('========================================')
    logger.info('Photo Upload Server Started')
    logger.info('========================================')

    app.run(
        host='0.0.0.0',
        port=5000,
        debug=False
    )