import os
import sys
import json
import subprocess
import struct
from pathlib import Path
from io import BytesIO

# ---------- 依赖检查 ----------
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
try:
    from pillow_heif import register_heif_opener
    HAS_HEIF = True
except ImportError:
    HAS_HEIF = False

if missing:
    print(f"缺少 Python 库: {', '.join(missing)}")
    print(f"请运行: pip install {' '.join(missing)}")
    sys.exit(1)

if not HAS_HEIF:
    print("警告: pillow-heif 未安装，HEIC/HEIF 文件可能无法被 Pillow 读取")
    print("安装命令: pip install pillow-heif")

# ---------- 配置 ----------
BASE_DIR = Path(__file__).resolve().parent
INCOMING_DIR = BASE_DIR / "incoming"
JSON_FILE = BASE_DIR / "photos.json"
ALLOWED_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.tiff', '.tif', '.webp', '.bmp', '.heic', '.heif'}

# ---------- 日期提取函数 ----------
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
        # HEIC/HEIF 支持：注册 opener（如果可用）
        if file_path and file_path.suffix.lower() in ('.heic', '.heif'):
            if HAS_HEIF:
                register_heif_opener()
            else:
                return 'x'  # 无 HEIF 支持则跳过 Pillow
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
        for key in ('EXIF DateTimeOriginal', 'Image DateTimeOriginal',
                    'EXIF DateTimeDigitized', 'Image DateTime'):
            if key in tags:
                return str(tags[key])
        return 'x'
    except:
        return 'x'

def parse_png_text(file_bytes):
    """从 PNG tEXt/iTXt 块提取创建时间"""
    try:
        data = file_bytes
        pos = 8
        while pos < len(data):
            length = struct.unpack('>I', data[pos:pos+4])[0]
            chunk_type = data[pos+4:pos+8].decode('ascii', errors='ignore')
            if chunk_type in ('tEXt', 'iTXt'):
                keyword_end = data.index(0, pos+8, pos+8+length)
                keyword = data[pos+8:keyword_end].decode('latin-1', errors='ignore')
                value = data[keyword_end+1:pos+8+length].decode('latin-1', errors='ignore')
                if 'creation' in keyword.lower() or 'date' in keyword.lower():
                    return value
            pos += 12 + length
    except:
        pass
    return None

def parse_exiftool(file_path):
    """调用系统 exiftool 获取日期（支持所有格式，包括 HEIC）"""
    try:
        result = subprocess.run(
            ['exiftool', '-DateTimeOriginal', '-CreateDate', '-ModifyDate', '-j', str(file_path)],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode != 0:
            return 'x'
        data = json.loads(result.stdout)[0]
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
        ext = file_path.suffix.lower()
        print(f"处理: {fname}")

        with open(file_path, 'rb') as f:
            data = f.read()

        # PNG 特殊处理：先尝试文本块
        if ext == '.png':
            png_date = parse_png_text(data)
            if png_date:
                # 如果从 PNG 文本块读到了日期，强制填入所有库（因为其他库可能读不到）
                result["piexif"][fname] = png_date
                result["Pillow"][fname] = png_date
                result["exifread"][fname] = png_date
                result["exiftool"][fname] = png_date
                continue

        result["piexif"][fname] = parse_piexif(data)
        result["Pillow"][fname] = parse_pillow(data, file_path)
        result["exifread"][fname] = parse_exifread(data)
        result["exiftool"][fname] = parse_exiftool(file_path)

    with open(JSON_FILE, 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    print(f"完成，结果保存至 {JSON_FILE}")

if __name__ == '__main__':
    main()