import os
import json
from pathlib import Path

# ---------- 依赖库 ----------
try:
    import piexif
    HAS_PIEXIF = True
except ImportError:
    HAS_PIEXIF = False

try:
    from PIL import Image
    HAS_PILLOW = True
except ImportError:
    HAS_PILLOW = False

try:
    import exifread
    HAS_EXIFREAD = True
except ImportError:
    HAS_EXIFREAD = False

# ---------- 配置 ----------
BASE_DIR = Path(__file__).resolve().parent
INCOMING_DIR = BASE_DIR / "incoming"          # 放图片的文件夹
JSON_FILE = BASE_DIR / "photos.json"

ALLOWED_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.tiff', '.tif', '.webp', '.bmp'}

# ---------- 各库日期提取 ----------
def parse_piexif(file_bytes):
    if not HAS_PIEXIF:
        return '库未安装'
    try:
        exif_dict = piexif.load(file_bytes)
        for ifd_name in ("Exif", "0th"):
            ifd = exif_dict.get(ifd_name, {})
            for tag_id in (36867, 36868, 306):   # DateTimeOriginal, DateTimeDigitized, DateTime
                if tag_id in ifd:
                    val = ifd[tag_id]
                    return val.decode('utf-8', errors='ignore') if isinstance(val, bytes) else str(val)
        return 'x'
    except Exception:
        return 'x'

def parse_pillow(file_bytes):
    if not HAS_PILLOW:
        return '库未安装'
    try:
        from io import BytesIO
        img = Image.open(BytesIO(file_bytes))
        exif = img._getexif()
        if exif is None:
            return 'x'
        for tag_id in (36867, 36868, 306):
            if tag_id in exif:
                return str(exif[tag_id])
        return 'x'
    except Exception:
        return 'x'

def parse_exifread(file_bytes):
    if not HAS_EXIFREAD:
        return '库未安装'
    try:
        from io import BytesIO
        tags = exifread.process_file(BytesIO(file_bytes))
        for key in ('EXIF DateTimeOriginal', 'Image DateTimeOriginal',
                    'EXIF DateTimeDigitized', 'Image DateTime'):
            if key in tags:
                return str(tags[key])
        return 'x'
    except Exception:
        return 'x'

# ---------- 主逻辑 ----------
def main():
    # 结果字典，严格只有三个库
    result = {
        "piexif": {},
        "Pillow": {},
        "exifread": {}
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
        result["Pillow"][fname] = parse_pillow(data)
        result["exifread"][fname] = parse_exifread(data)

    with open(JSON_FILE, 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    print(f"完成，结果已保存至 {JSON_FILE}")

if __name__ == '__main__':
    main()