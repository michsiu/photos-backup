import os
import sys
import json
import struct
import subprocess
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
    print("⚠️ 警告: pillow-heif 未安装，HEIC/HEIF 文件可能无法被 Pillow 读取")
    print("   安装命令: pip install pillow-heif")

# ---------- 配置 ----------
BASE_DIR = Path(__file__).resolve().parent
INCOMING_DIR = BASE_DIR / "incoming"
JSON_FILE = BASE_DIR / "photos.json"
ALLOWED_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.tiff', '.tif', '.webp', '.bmp', '.heic', '.heif'}

# ---------- PNG eXIf 块提取 ----------
def get_exif_from_png(file_bytes):
    """从 PNG 的 eXIf 块中提取 EXIF 字典，失败返回 None"""
    try:
        pos = 8  # 跳过 PNG 签名
        while pos < len(file_bytes):
            if pos + 12 > len(file_bytes):
                break
            length = struct.unpack('>I', file_bytes[pos:pos+4])[0]
            chunk_type = file_bytes[pos+4:pos+8].decode('ascii', errors='ignore')
            if chunk_type == 'eXIf':
                exif_bytes = file_bytes[pos+8:pos+8+length]
                # 使用 piexif 解析二进制 EXIF 数据
                return piexif.load(exif_bytes)
            pos += 12 + length
    except Exception:
        pass
    return None

def extract_date_from_exif_dict(exif_dict):
    """从 piexif 的字典结构中提取日期字符串"""
    if not exif_dict:
        return None
    for ifd_name in ("Exif", "0th"):
        ifd = exif_dict.get(ifd_name, {})
        for tag_id in (36867, 36868, 306):  # DateTimeOriginal, DateTimeDigitized, DateTime
            if tag_id in ifd:
                val = ifd[tag_id]
                if isinstance(val, bytes):
                    return val.decode('utf-8', errors='ignore')
                return str(val)
    return None

# ---------- 各库日期提取函数 ----------
def parse_piexif(file_bytes, is_png=False):
    """piexif 解析，如果是 PNG 且已有 eXIf 则走特殊路径"""
    if is_png:
        exif_dict = get_exif_from_png(file_bytes)
        if exif_dict:
            return extract_date_from_exif_dict(exif_dict) or 'x'
        return 'x'
    try:
        exif_dict = piexif.load(file_bytes)
        return extract_date_from_exif_dict(exif_dict) or 'x'
    except:
        return 'x'

def parse_pillow(file_bytes, file_path=None):
    """Pillow 解析，支持 PNG eXIf 和 HEIC"""
    if file_path and file_path.suffix.lower() == '.png':
        exif_dict = get_exif_from_png(file_bytes)
        if exif_dict:
            return extract_date_from_exif_dict(exif_dict) or 'x'
    try:
        if file_path and file_path.suffix.lower() in ('.heic', '.heif') and HAS_HEIF:
            register_heif_opener()
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
    """exifread 解析，支持 JPEG 和 PNG"""
    try:
        tags = exifread.process_file(BytesIO(file_bytes))
        for key in ('EXIF DateTimeOriginal', 'Image DateTimeOriginal',
                    'EXIF DateTimeDigitized', 'Image DateTime'):
            if key in tags:
                return str(tags[key])
        return 'x'
    except:
        return 'x'

def parse_exiftool(file_path):
    """调用系统 ExifTool 获取日期，覆盖所有常见标签"""
    try:
        result = subprocess.run(
            ['exiftool', '-json', str(file_path)],
            capture_output=True, text=True, timeout=10
        )
        data = json.loads(result.stdout)[0]
        for tag in ('DateTimeOriginal', 'CreateDate', 'ModifyDate',
                    'XMP:CreateDate', 'XMP:DateTimeOriginal',
                    'QuickTime:CreateDate', 'QuickTime:ModifyDate',
                    'MediaCreateDate', 'MediaModifyDate',
                    'PNG:CreationTime', 'EXIF:DateTimeOriginal'):
            val = data.get(tag)
            if val and val.strip():
                return val.strip()
        return 'x'
    except FileNotFoundError:
        return 'exiftool未安装'
    except:
        return 'x'

# ---------- 主处理逻辑 ----------
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

        is_png = (ext == '.png')

        # PNG 特殊处理：先尝试 eXIf 块，如果成功则直接填入所有库（避免重复解析）
        png_exif_date = None
        if is_png:
            exif_dict = get_exif_from_png(data)
            if exif_dict:
                png_exif_date = extract_date_from_exif_dict(exif_dict)

        if png_exif_date:
            # 所有库统一填写为 PNG 内嵌的 EXIF 日期
            result["piexif"][fname] = png_exif_date
            result["Pillow"][fname] = png_exif_date
            result["exifread"][fname] = png_exif_date
            result["exiftool"][fname] = png_exif_date
            continue

        # 常规处理
        result["piexif"][fname] = parse_piexif(data, is_png=is_png)
        result["Pillow"][fname] = parse_pillow(data, file_path)
        result["exifread"][fname] = parse_exifread(data)
        result["exiftool"][fname] = parse_exiftool(file_path)

    with open(JSON_FILE, 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    print(f"✅ 处理完成，结果保存至 {JSON_FILE}")

if __name__ == '__main__':
    main()