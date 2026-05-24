import os
import io
import json
import hashlib
import datetime
import tempfile
import shutil
import re
from pathlib import Path
from flask import Flask, request, render_template_string, jsonify
from PIL import Image, ExifTags
import piexif

app = Flask(__name__)

UPLOAD_FOLDER = Path('photos')
THUMB_FOLDER = Path('thumbs')
JSON_FILE = Path('photos.json')
ALLOWED_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.tiff'}

# 读取已有的 photos.json
if JSON_FILE.exists():
    with open(JSON_FILE, 'r') as f:
        photos_db = json.load(f)
else:
    photos_db = {}

# HTML 模板
UPLOAD_PAGE = '''
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <title>上传照片</title>
  <style>
    body { font-family: sans-serif; max-width: 600px; margin: 50px auto; padding: 20px; }
    .progress { margin-top: 10px; }
    button { margin-top: 20px; padding: 10px 20px; }
    ul { list-style: none; padding: 0; }
    li { margin: 5px 0; }
  </style>
</head>
<body>
  <h1>📷 批量上传照片</h1>
  <input type="file" id="fileInput" multiple accept="image/*">
  <button onclick="uploadFiles()">开始上传</button>
  <div class="progress" id="progress"></div>
  <hr>
  <button onclick="shutdown()">✅ 完成上传并关闭服务</button>
  <script>
    async function uploadFiles() {
      const files = document.getElementById('fileInput').files;
      if (files.length === 0) return alert('请选择文件');
      const progressDiv = document.getElementById('progress');
      progressDiv.innerHTML = '';
      let count = 0;
      for (const file of files) {
        const formData = new FormData();
        formData.append('image', file);
        try {
          const resp = await fetch('/upload', { method: 'POST', body: formData });
          const result = await resp.json();
          const li = document.createElement('li');
          li.textContent = `${file.name} → ${result.status} (${result.sha256?.slice(0,8)})`;
          progressDiv.appendChild(li);
          count++;
        } catch (err) {
          const li = document.createElement('li');
          li.textContent = `${file.name} → 失败: ${err}`;
          progressDiv.appendChild(li);
        }
      }
      alert(`上传完成，共处理 ${count} 个文件`);
    }
    async function shutdown() {
      await fetch('/shutdown', { method: 'POST' });
      alert('服务已关闭，页面将不可用');
    }
  </script>
</body>
</html>
'''

@app.route('/')
def index():
    return UPLOAD_PAGE

def get_exif_date(image_bytes: bytes) -> datetime.datetime | None:
    """从 EXIF 中提取原始日期，返回带时区的 datetime"""
    try:
        exif_dict = piexif.load(image_bytes)
        # 尝试获取 DateTimeOriginal (0x9003) 或 DateTimeDigitized (0x9004)
        for ifd_name in ['Exif', '0th']:
            ifd = exif_dict.get(ifd_name, {})
            for tag_id in [36867, 36868, 306]:  # DateTimeOriginal, DateTimeDigitized, DateTime
                if tag_id in ifd:
                    dt_str = ifd[tag_id].decode('utf-8', errors='ignore')
                    # 格式通常为 "YYYY:MM:DD HH:MM:SS"
                    naive_dt = datetime.datetime.strptime(dt_str, '%Y:%m:%d %H:%M:%S')
                    # 尝试获取 OffsetTime 或 OffsetTimeOriginal 等
                    offset_tag = None
                    if ifd_name == 'Exif':
                        # OffsetTimeOriginal (0x9010), OffsetTimeDigitized (0x9011)
                        offset_tag = ifd.get(0x9010) or ifd.get(0x9011)
                    if offset_tag:
                        offset_str = offset_tag.decode('utf-8', errors='ignore')
                        # 格式 "+08:00"
                        hours, minutes = map(int, offset_str.split(':'))
                        tz = datetime.timezone(datetime.timedelta(hours=hours, minutes=minutes))
                        return naive_dt.replace(tzinfo=tz)
                    # 若无时区信息，假设为 UTC（此处保守处理，但需求要求转为0时区）
                    # 我们暂不假定，返回 naive 并后续转为 UTC 会出错，所以我们直接返回 None 让调用者处理
                    return None  # 没有时区信息，交给文件名拆分逻辑
    except Exception:
        pass
    return None

def parse_date_from_filename(filename: str) -> datetime.datetime | None:
    """按 ==boundary== 拆分文件名，取前半部分为 ISO 日期（北京时间，含时区）"""
    if '==boundary==' not in filename:
        return None
    date_part, _ = filename.split('==boundary==', 1)
    date_part = date_part.strip()
    # 尝试解析 ISO 8601 格式，如 "2023-05-01T12:30:00+08:00"
    try:
        # Python 3.7+ fromisoformat 支持时区
        dt = datetime.datetime.fromisoformat(date_part)
        return dt
    except ValueError:
        # 可能缺少秒等，尝试其他格式
        for fmt in ['%Y-%m-%dT%H:%M:%S%z', '%Y-%m-%dT%H:%M%z', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%d %H:%M:%S%z']:
            try:
                if fmt.endswith('%z'):
                    return datetime.datetime.strptime(date_part, fmt)
                else:
                    # 无时区则视为北京时间 (+08:00)
                    dt_naive = datetime.datetime.strptime(date_part, fmt)
                    dt_bj = dt_naive.replace(tzinfo=datetime.timezone(datetime.timedelta(hours=8)))
                    return dt_bj
            except ValueError:
                continue
    return None

def get_utc_datetime(image_bytes: bytes, filename: str) -> datetime.datetime:
    """
    返回 UTC 时间（精确到秒，但需求精确到分秒，保留秒）
    优先 EXIF 日期（有时区），否则尝试文件名拆分，再否则使用当前 UTC 时间。
    """
    dt = get_exif_date(image_bytes)
    if dt is not None:
        return dt.astimezone(datetime.timezone.utc)
    dt = parse_date_from_filename(filename)
    if dt is not None:
        return dt.astimezone(datetime.timezone.utc)
    # 兜底：当前 UTC 时间
    return datetime.datetime.now(datetime.timezone.utc)

def get_original_filename(filename: str) -> str:
    """从可能包含 bounday 的文件名中提取真实文件名"""
    if '==boundary==' in filename:
        _, real_name = filename.split('==boundary==', 1)
        return real_name.strip()
    return filename

@app.route('/upload', methods=['POST'])
def upload():
    if 'image' not in request.files:
        return jsonify({'status': 'error', 'message': '没有文件'}), 400
    file = request.files['image']
    if file.filename == '':
        return jsonify({'status': 'error', 'message': '空文件名'}), 400

    # 读取全部内容
    image_bytes = file.read()
    # 计算 SHA256
    sha256 = hashlib.sha256(image_bytes).hexdigest()
    # 原始文件名（处理后）
    original_name = get_original_filename(file.filename)
    ext = os.path.splitext(original_name)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        return jsonify({'status': 'error', 'message': f'不支持的文件类型 {ext}'}), 400

    # 获取日期和时间
    utc_dt = get_utc_datetime(image_bytes, file.filename)
    year = str(utc_dt.year)
    date_str = utc_dt.strftime('%Y-%m-%dT%H:%M:%SZ')  # ISO 8601 UTC

    # 目标路径
    photo_rel = f'photos/{year}/{sha256}{ext}'
    thumb_rel = f'thumbs/{year}/{sha256}{ext}'
    photo_abs = Path(photo_rel)
    thumb_abs = Path(thumb_rel)
    photo_abs.parent.mkdir(parents=True, exist_ok=True)
    thumb_abs.parent.mkdir(parents=True, exist_ok=True)

    # 保存原始图片
    with open(photo_abs, 'wb') as f:
        f.write(image_bytes)

    # 生成缩略图
    try:
        img = Image.open(io.BytesIO(image_bytes))
        img.thumbnail((400, 400))  # 最大尺寸 400x400
        # 处理透明度（如 PNG）
        if img.mode in ('RGBA', 'LA') or (img.mode == 'P' and 'transparency' in img.info):
            # 转换为 RGB
            img = img.convert('RGB')
        img.save(thumb_abs)
    except Exception as e:
        # 缩略图生成失败，复制原图
        shutil.copy(photo_abs, thumb_abs)
        print(f'Thumbnail failed for {sha256}: {e}')

    # 构造 raw 文件 URL（需要仓库名和分支）
    repo = os.environ.get('GITHUB_REPOSITORY', 'user/repo')
    branch = os.environ.get('GITHUB_REF', 'refs/heads/main').replace('refs/heads/', '')
    raw_base = f'https://raw.githubusercontent.com/{repo}/{branch}'
    url = photo_rel
    thumb_url = thumb_rel

    # 更新数据库
    photos_db[sha256] = {
        'fileName': original_name,
        'url': url,
        'thumbnail': thumb_url,
        'year': year,
        'date': date_str,
        'sha256': sha256
    }

    # 实时写入 photos.json
    with open(JSON_FILE, 'w') as f:
        json.dump(photos_db, f, indent=2, ensure_ascii=False)

    return jsonify({'status': 'ok', 'sha256': sha256, 'url': url})

@app.route('/shutdown', methods=['POST'])
def shutdown():
    """关闭 Flask 服务，触发工作流后续步骤"""
    func = request.environ.get('werkzeug.server.shutdown')
    if func is None:
        # 非 werkzeug 服务器，尝试 os._exit
        os._exit(0)
    func()
    return 'Server shutting down...'

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)