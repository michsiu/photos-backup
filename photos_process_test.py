import os
import json
import struct
from pathlib import Path

# ---------- 依赖库（按需安装） ----------
try:
    import exifread
    HAS_EXIFREAD = True
except:
    HAS_EXIFREAD = False

try:
    from PIL import Image
    from PIL.ExifTags import TAGS
    HAS_PIL = True
except:
    HAS_PIL = False

try:
    import piexif
    HAS_PIEXIF = True
except:
    HAS_PIEXIF = False

# ---------- 配置 ----------
BASE_DIR = Path(__file__).resolve().parent
INCOMING_DIR = BASE_DIR / "incoming"          # 图片文件夹
JSON_FILE = BASE_DIR / "photos.json"
ALLOWED_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.tiff', '.tif', '.webp', '.bmp', '.heic', '.heif'}

# ---------- 通用日期提取函数 ----------
def extract_date_from_bytes(file_bytes, file_path):
    """使用多种方法尝试提取日期，返回字符串或'x'"""
    dates = []

    # 方法1：exifread（支持PNG、JPEG、HEIC）
    if HAS_EXIFREAD:
        try:
            from io import BytesIO
            tags = exifread.process_file(BytesIO(file_bytes), details=False)
            # 查找所有可能包含日期的键
            for key in tags:
                if 'DateTime' in key or 'Date' in key or 'Time' in key:
                    val = str(tags[key]).strip()
                    if val and not val.startswith('0000'):
                        dates.append(val)
        except:
            pass

    # 方法2：Pillow 遍历所有 EXIF 标签
    if HAS_PIL:
        try:
            from io import BytesIO
            img = Image.open(BytesIO(file_bytes))
            exif_data = img._getexif()
            if exif_data:
                for tag_id, value in exif_data.items():
                    tag_name = TAGS.get(tag_id, '')
                    if any(kw in tag_name.lower() for kw in ['datetime', 'date', 'time']):
                        dates.append(str(value))
        except:
            pass

    # 方法3：piexif（主要处理JPEG）
    if HAS_PIEXIF:
        try:
            exif_dict = piexif.load(file_bytes)
            for ifd in ['Exif', '0th', 'GPS']:
                data = exif_dict.get(ifd, {})
                for tag in data:
                    if isinstance(data[tag], bytes):
                        val = data[tag].decode('utf-8', errors='ignore')
                        if '20' in val:  # 粗略判断含年份
                            dates.append(val)
        except:
            pass

    # 方法4：手动解析 PNG 的 tEXt/iTXt 块（寻找创建时间）
    if file_path.suffix.lower() == '.png':
        try:
            # 读取 PNG 块
            data = file_bytes
            pos = 8  # 跳过 PNG 签名
            while pos < len(data):
                length = struct.unpack('>I', data[pos:pos+4])[0]
                chunk_type = data[pos+4:pos+8].decode('ascii', errors='ignore')
                if chunk_type in ('tEXt', 'iTXt'):
                    keyword_end = data.index(0, pos+8, pos+8+length)
                    keyword = data[pos+8:keyword_end].decode('latin-1', errors='ignore')
                    value = data[keyword_end+1:pos+8+length].decode('latin-1', errors='ignore')
                    if 'creation' in keyword.lower() or 'date' in keyword.lower():
                        dates.append(value)
                pos += 12 + length
        except:
            pass

    # 去重并返回第一个有效日期
    seen = set()
    unique_dates = []
    for d in dates:
        if d not in seen:
            seen.add(d)
            unique_dates.append(d)
    return unique_dates[0] if unique_dates else 'x'

# ---------- 主程序 ----------
def main():
    result = {"Pillow+": {}, "piexif+": {}, "exifread+": {}, "combined": {}}
    
    if not INCOMING_DIR.exists():
        print(f"文件夹不存在: {INCOMING_DIR}")
        return

    image_files = [p for p in INCOMING_DIR.iterdir() if p.is_file() and p.suffix.lower() in ALLOWED_EXTENSIONS]
    if not image_files:
        print("无图片文件")
        with open(JSON_FILE, 'w') as f:
            json.dump(result, f, indent=2)
        return

    for file_path in image_files:
        fname = file_path.name
        print(f"处理: {fname}")
        with open(file_path, 'rb') as f:
            data = f.read()

        # 分别用各库（实际均使用增强提取）
        date_pillow = extract_date_from_bytes(data, file_path)  # 代表Pillow路径
        date_piexif = extract_date_from_bytes(data, file_path)
        date_exifread = extract_date_from_bytes(data, file_path)
        date_combined = extract_date_from_bytes(data, file_path)  # 综合结果

        result["Pillow+"][fname] = date_pillow
        result["piexif+"][fname] = date_piexif
        result["exifread+"][fname] = date_exifread
        result["combined"][fname] = date_combined

    with open(JSON_FILE, 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    print(f"完成，结果保存至 {JSON_FILE}")

if __name__ == '__main__':
    main()