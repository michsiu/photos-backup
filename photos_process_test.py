import os
import sys
import json
import subprocess
from pathlib import Path
from io import BytesIO

# ---------- 依赖检查与导入 ----------
missing = []
try:
    import piexif
except ImportError:
    missing.append('piexif')
try:
    from PIL import Image
except ImportError:
    missing.append('Pillow')
try:
    import exifread
except ImportError:
    missing.append('exifread')

if missing:
    print(f"缺少以下 Python 库: {', '.join(missing)}")
    print(f"请运行: pip install {' '.join(missing)}")
    sys.exit(1)

# ---------- 配置 ----------
BASE_DIR = Path(__file__).resolve().parent
INCOMING_DIR = BASE_DIR / "incoming"
JSON_FILE = BASE_DIR / "photos.json"
ALLOWED_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.tiff', '.tif', '.webp', '.bmp', '.heic', '.heif'}

# ---------- 各库日期提取 ----------
def parse_piexif(file_bytes):
    try:
        exif_dict = piexif.load(file_bytes)
        for ifd_name in ("Exif", "0th"):
            ifd = exif_dict.get(ifd_name, {})
            for tag_id in (36867, 36868, 306):
                if tag_id in ifd:
                    val = ifd[tag_id]
                    return val.decode('utf-8', errors='ignore') if isinstance(val, bytes) else str(val)
        return 'x'
    except:
        return 'x'

def parse_pillow(file_bytes, file_path=None):
    try:
        if file_path and file_path.suffix.lower() in ('.heic', '.heif'):
            try:
                from pillow_heif import register_heif_opener
                register_heif_opener()
            except ImportError:
                pass
        img = Image.open(BytesIO(file_bytes))
        exif = img._getexif()
        if exif:
            for tag_id in (36867, 36868, 306):
                if tag_id in exif:
                    return str(exif[tag_id])
        return 'x'
    except:
        return 'x'

def parse_exifread(file_bytes):
    try:
        tags = exifread.process_file(BytesIO(file_bytes))
        for key in ('EXIF DateTimeOriginal', 'Image DateTimeOriginal', 'EXIF DateTimeDigitized', 'Image DateTime'):
            if key in tags:
                return str(tags[key])
        return 'x'
    except:
        return 'x'

def parse_exiftool(file_path):
    """调用系统 exiftool 获取日期"""
    try:
        result = subprocess.run(
            ['exiftool', '-DateTimeOriginal', '-CreateDate', '-ModifyDate', '-j', str(file_path)],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode != 0:
            return 'x'
        data = json.loads(result.stdout)[0]
        # 优先级：DateTimeOriginal > CreateDate > ModifyDate
        for tag in ('DateTimeOriginal', 'CreateDate', 'ModifyDate'):
            val = data.get(tag)
            if val and val.strip():
                return val.strip()
        return 'x'
    except FileNotFoundError:
        return 'exiftool未安装'
    except:
        return 'x'

# ---------- 主逻辑 ----------
def main():
    result = {
        "piexif": {},
        "Pillow": {},
        "exifread": {},
        "exiftool": {}
    }

    if not INCOMING_DIR.exists():
        print(f"文件夹不存在：{INCOMING_DIR}")
        return

    image_files = [p for p in INCOMING_DIR.iterdir()
                   if p.is_file() and p.suffix.lower() in ALLOWED_EXTENSIONS]

    if not image_files:
        print("没有找到支持的图片文件")
        with open(JSON_FILE, 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        return

    for file_path in image_files:
        fname = file_path.name
        print(f"处理: {fname}")
        with open(file_path, 'rb') as f:
            data = f.read()

        result["piexif"][fname] = parse_piexif(data)
        result["Pillow"][fname] = parse_pillow(data, file_path)
        result["exifread"][fname] = parse_exifread(data)
        result["exiftool"][fname] = parse_exiftool(file_path)

    with open(JSON_FILE, 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    print(f"完成，结果保存至 {JSON_FILE}")

if __name__ == '__main__':
    main()