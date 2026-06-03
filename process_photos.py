import os
import io
import json
import hashlib
import datetime
import shutil
import re
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from PIL import Image
import exifread

BASE_DIR = Path(__file__).resolve().parent
INCOMING_DIR = BASE_DIR / "incoming"
PHOTO_DIR = BASE_DIR / "photos"
THUMB_DIR = BASE_DIR / "thumbs"
JSON_FILE = BASE_DIR / "photos.json"
FAILED_FILE = BASE_DIR / "failed_task.txt"          # 新增：记录无日期且无boundary的文件

PHOTO_DIR.mkdir(parents=True, exist_ok=True)
THUMB_DIR.mkdir(parents=True, exist_ok=True)

ALLOWED_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.tiff'}

# 加载现有数据库
if JSON_FILE.exists():
    with open(JSON_FILE, "r", encoding="utf-8") as f:
        photos_db = json.load(f)
else:
    photos_db = {}

import threading
db_lock = threading.Lock()

def log(msg):
    print(f"[PROCESS] {msg}", flush=True)

def get_exif_datetime(image_bytes):
    """使用 exifread 读取 DateTimeOriginal，返回 naive datetime 或 None"""
    try:
        tags = exifread.process_file(io.BytesIO(image_bytes))
        for key in ('EXIF DateTimeOriginal', 'Image DateTimeOriginal',
                    'EXIF DateTimeDigitized', 'Image DateTime'):
            if key in tags:
                dt_str = str(tags[key])
                try:
                    return datetime.datetime.strptime(dt_str, "%Y:%m:%d %H:%M:%S")
                except ValueError:
                    continue
        return None
    except Exception:
        return None

def parse_date_from_boundary(filename):
    """从文件名中的 ==boundary== 前提取日期时间"""
    if "==boundary==" not in filename:
        return None
    date_part = filename.split("==boundary==", 1)[0].strip()
    # 尝试带时区的格式
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S%Z",
                "%Y-%m-%d %H:%M:%S%z", "%Y-%m-%dT%H:%M%z", "%Y-%m-%d %H:%M%z"):
        try:
            return datetime.datetime.strptime(date_part, fmt)
        except ValueError:
            continue
    # 尝试不带时区的格式，假设为北京时间（UTC+8）
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M"):
        try:
            naive = datetime.datetime.strptime(date_part, fmt)
            return naive.replace(tzinfo=datetime.timezone(datetime.timedelta(hours=8)))
        except ValueError:
            continue
    return None

def get_real_filename(raw_name):
    """去除 boundary 前缀，返回真实文件名"""
    if "==boundary==" in raw_name:
        return raw_name.split("==boundary==", 1)[1].strip()
    return raw_name

def process_one(file_path: Path):
    """处理单个图片文件，返回 True 表示成功"""
    try:
        fname = file_path.name
        ext = file_path.suffix.lower()
        if ext not in ALLOWED_EXTENSIONS:
            log(f"跳过非图片文件: {fname}")
            return False

        with open(file_path, "rb") as f:
            data = f.read()

        sha = hashlib.sha256(data).hexdigest()

        # 如果已存在，跳过
        with db_lock:
            if sha in photos_db:
                log(f"跳过重复图片: {fname} (SHA 已存在)")
                file_path.unlink()
                return True

        # ---------- 日期获取（优先 EXIF，其次 boundary，否则记录失败并回退到当前时间） ----------
        dt_utc = None
        exif_dt = get_exif_datetime(data)
        if exif_dt is not None:
            dt_utc = exif_dt.replace(tzinfo=datetime.timezone.utc)
        else:
            boundary_dt = parse_date_from_boundary(fname)
            if boundary_dt is not None:
                dt_utc = boundary_dt.astimezone(datetime.timezone.utc)
            else:
                # 既无 EXIF 日期，也无 boundary 前缀 → 记录到 failed_task.txt
                with open(FAILED_FILE, "a", encoding="utf-8") as fail_f:
                    fail_f.write(f"{fname}\n")
                dt_utc = datetime.datetime.now(datetime.timezone.utc)

        year = str(dt_utc.year)
        date_iso = dt_utc.strftime("%Y-%m-%dT%H:%M:%SZ")

        # 目标路径
        photo_rel = f"photos/{year}/{sha}{ext}"
        thumb_rel = f"thumbs/{year}/{sha}{ext}"
        photo_path = BASE_DIR / photo_rel
        thumb_path = BASE_DIR / thumb_rel
        photo_path.parent.mkdir(parents=True, exist_ok=True)
        thumb_path.parent.mkdir(parents=True, exist_ok=True)

        # 移动原图
        shutil.move(str(file_path), str(photo_path))

        # 生成缩略图
        try:
            img = Image.open(io.BytesIO(data))
            img.thumbnail((400, 400))
            if img.mode in ("RGBA", "LA", "P"):
                img = img.convert("RGB")
            img.save(thumb_path)
        except Exception as e:
            log(f"缩略图失败 {fname}: {e}")
            shutil.copyfile(photo_path, thumb_path)

        real_name = get_real_filename(fname)
        entry = {
            "fileName": real_name,
            "url": photo_rel,
            "thumbnail": thumb_rel,
            "year": year,
            "date": date_iso,
            "sha256": sha
        }

        with db_lock:
            photos_db[sha] = entry

        log(f"已处理: {fname} -> {photo_rel}")
        return True

    except Exception as e:
        log(f"处理失败 {file_path.name}: {e}")
        return False

def main():
    files = [p for p in INCOMING_DIR.iterdir() if p.is_file()]
    if not files:
        log("没有待处理文件")
        return

    log(f"发现 {len(files)} 个文件，开始并发处理...")
    success = 0
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {executor.submit(process_one, fp): fp for fp in files}
        for future in as_completed(futures):
            if future.result():
                success += 1

    # 保存 JSON
    with db_lock:
        tmp_json = JSON_FILE.with_suffix(".tmp")
        with open(tmp_json, "w", encoding="utf-8") as f:
            json.dump(photos_db, f, indent=2, ensure_ascii=False)
        tmp_json.replace(JSON_FILE)

    log(f"处理完成: {success}/{len(files)} 成功，photos.json 已更新。")

    # 清理 incoming 残留
    for f in INCOMING_DIR.iterdir():
        if f.is_file():
            f.unlink()

if __name__ == "__main__":
    main()