import os
import json
from pathlib import Path

# ---------- 第三方库导入（尝试导入，如果缺失则相关结果标记为“库未安装”） ----------
try:
    import piexif
    HAS_PIEXIF = True
except ImportError:
    HAS_PIEXIF = False

try:
    from PIL import Image
    from PIL.ExifTags import TAGS
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

try:
    import exifread
    HAS_EXIFREAD = True
except ImportError:
    HAS_EXIFREAD = False

# ---------- 配置 ----------
BASE_DIR = Path(__file__).resolve().parent
INCOMING_DIR = BASE_DIR / "incoming"          # 图片文件夹，可以修改为其他路径
JSON_FILE = BASE_DIR / "photos.json"          # 输出 JSON 文件

ALLOWED_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.tiff', '.heic', '.tif', '.webp', '.bmp'}

# ---------- 各库日期提取函数 ----------
def parse_piexif(file_bytes):
    """使用 piexif 读取 DateTimeOriginal，返回字符串或 'x'"""
    if not HAS_PIEXIF:
        return "库未安装"
    try:
        exif_dict = piexif.load(file_bytes)
        for ifd_name in ("Exif", "0th"):
            ifd = exif_dict.get(ifd_name, {})
            for tag in (36867, 36868, 306):  # DateTimeOriginal, DateTimeDigitized, DateTime
                if tag in ifd:
                    val = ifd[tag]
                    if isinstance(val, bytes):
                        return val.decode("utf-8", errors="ignore")
                    return str(val)
        return "x"
    except Exception:
        return "x"

def parse_pillow(file_bytes):
    """使用 Pillow 读取 DateTimeOriginal，返回字符串或 'x'"""
    if not HAS_PIL:
        return "库未安装"
    try:
        from io import BytesIO
        img = Image.open(BytesIO(file_bytes))
        exif_data = img._getexif()
        if exif_data is None:
            return "x"
        # 日期标签 ID 36867 对应 DateTimeOriginal
        date = exif_data.get(36867)
        if date:
            return str(date)
        # 尝试其他常见标签
        for tag_id in (36868, 306):
            if tag_id in exif_data:
                return str(exif_data[tag_id])
        return "x"
    except Exception:
        return "x"

def parse_exifread(file_bytes):
    """使用 exifread 读取 DateTimeOriginal，返回字符串或 'x'"""
    if not HAS_EXIFREAD:
        return "库未安装"
    try:
        from io import BytesIO
        tags = exifread.process_file(BytesIO(file_bytes))
        # 可能的键名
        for key in ('EXIF DateTimeOriginal', 'Image DateTimeOriginal', 'EXIF DateTimeDigitized', 'Image DateTime'):
            if key in tags:
                return str(tags[key])
        return "x"
    except Exception:
        return "x"

# ---------- 主处理逻辑 ----------
def main():
    # 准备结果字典
    result = {
        "piexif": {},
        "Pillow": {},
        "exifread": {}
    }

    # 确保目标文件夹存在
    if not INCOMING_DIR.exists():
        print(f"文件夹不存在：{INCOMING_DIR}")
        return

    # 收集所有图片文件
    image_files = [p for p in INCOMING_DIR.iterdir() 
                   if p.is_file() and p.suffix.lower() in ALLOWED_EXTENSIONS]

    if not image_files:
        print("没有找到图片文件")
        # 保存空 JSON
        with open(JSON_FILE, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        return

    for file_path in image_files:
        fname = file_path.name
        print(f"正在处理: {fname}")

        # 读取文件二进制数据（各库复用）
        with open(file_path, "rb") as f:
            data = f.read()

        # 获取各库解析结果
        date_piexif = parse_piexif(data)
        date_pillow = parse_pillow(data)
        date_exifread = parse_exifread(data)

        # 写入结果字典
        result["piexif"][fname] = date_piexif
        result["Pillow"][fname] = date_pillow
        result["exifread"][fname] = date_exifread

    # 保存 JSON
    with open(JSON_FILE, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    print(f"处理完成，结果已保存至 {JSON_FILE}")

if __name__ == "__main__":
    main()