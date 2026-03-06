import os
import json
import time
import psutil
import sys
import traceback
from datetime import datetime
from PIL import Image
from path_manager import HISTORY_DIR, IMAGES_DIR, LOG_FILE
import messenger
from config_manager import save_config

def log_to_file(msg, level="INFO"):
    """app_debug.log 파일에 로그를 기록합니다."""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"[{ts}] [{level}] {msg}\n")
    except: pass

def handle_exception(exc_type, exc_value, exc_traceback):
    """처리되지 않은 예외를 포착하여 로그에 기록합니다."""
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
    err_msg = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
    log_to_file(f"CRITICAL UNHANDLED EXCEPTION:\n{err_msg}", "CRITICAL")
    sys.__excepthook__(exc_type, exc_value, exc_traceback)

def setup_dpi_awareness():
    """Windows 고해상도 DPI 설정을 적용합니다."""
    if sys.platform == "win32":
        import ctypes
        try:
            # Per Monitor V2 DPI Awareness
            ctypes.windll.user32.SetProcessDpiAwarenessContext(-4)
        except:
            try: ctypes.windll.shcore.SetProcessDpiAwareness(1)
            except: pass
    os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "1"

def fmt_time(s):
    """초 단위 시간을 HH:MM:SS 형식으로 변환합니다."""
    if s is None or s < 0:
        return "—"
    m, s = divmod(int(s), 60)
    h, m = divmod(m, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"

def get_latest_render_file():
    """가장 최근의 렌더링 JSON 파일을 가져옵니다."""
    if not os.path.isdir(HISTORY_DIR): return None
    files = [f for f in os.listdir(HISTORY_DIR) if f.startswith("Render_") and f.endswith(".json")]
    if not files: return None
    files.sort(reverse=True)
    return os.path.join(HISTORY_DIR, files[0])

def determine_render_status(info, upd, end):
    """JSON 데이터를 기반으로 현재 렌더링 상태를 판정합니다."""
    end_ts = end.get("end_ts", -1)
    ren = upd.get("rendered_frames", 0)
    tot = info.get("total_frames", 0)
    
    if end_ts is None or end_ts <= 0:
        return "Progress"
    if ren >= tot > 0:
        return "Finished"
    return "Stopped"

def resolve_image_path(raw_path):
    """원본 경로 또는 지원되는 확장자를 탐색하여 유효한 이미지 경로를 반환합니다."""
    if not raw_path:
        return None
        
    SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tga"}
    
    # 1. 원본 경로가 존재할 경우 즉시 반환
    if os.path.exists(raw_path):
        return raw_path
        
    # 2. 확장자가 없거나 틀릴 경우 지원되는 확장자들로 재탐색
    base, _ = os.path.splitext(raw_path)
    for ext in SUPPORTED_EXTENSIONS:
        test_p = base + ext
        if os.path.exists(test_p):
            return test_p
            
    return None

def get_status_color_from_file(path, color_map):
    """파일에서 데이터를 직접 읽어 상태 색상을 결정합니다."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        status = determine_render_status(data.get("start", {}), data.get("update", {}), data.get("end", {}))
        
        if status == "Progress": return color_map['YELLOW']
        if status == "Finished": return color_map['GREEN']
        return color_map['RED']
    except: 
        return color_map['RED']

def force_update_json_on_crash(target_path):
    """프로세스 종료 시 JSON에 종료 기록을 강제로 기입합니다."""
    if target_path and os.path.exists(target_path):
        try:
            with open(target_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            end_info = data.get("end", {})
            if end_info.get("end_ts", -1) <= 0:
                now_ts = time.time()
                data["end"] = {
                    "end_ts": now_ts,
                    "end_time": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(now_ts))
                }
                with open(target_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                return True
        except Exception:
            pass
    return False

def process_thumbnail(actual_source, thumb_path):
    """Pillow를 사용하여 썸네일을 생성하고 저장합니다."""
    try:
        with Image.open(actual_source) as img:
            target_size = (240, 135)
            
            # JPEG 전용 드래프트 최적화
            if actual_source.lower().endswith((".jpg", ".jpeg")):
                img.draft(img.mode, target_size)
            
            # 썸네일 생성
            img.thumbnail(target_size, resample=Image.Resampling.NEAREST)
            
            # 16:9 패딩 배경 작업
            bg = Image.new("RGB", target_size, (11, 11, 11))
            paste_x = (target_size[0] - img.width) // 2
            paste_y = (target_size[1] - img.height) // 2
            
            is_transparent = (img.mode in ("RGBA", "P"))
            if is_transparent:
                bg_path = os.path.join(IMAGES_DIR, "BG_Transparent.png")
                if os.path.exists(bg_path):
                    with Image.open(bg_path) as bg_img:
                        pattern = bg_img.convert("RGB").resize(target_size, Image.Resampling.NEAREST)
                        img_bg = pattern.crop((paste_x, paste_y, paste_x + img.width, paste_y + img.height))
                        if img.mode == "RGBA":
                            img_bg.paste(img, mask=img.split()[3])
                        else:
                            img_bg.paste(img)
                        bg.paste(img_bg, (paste_x, paste_y))
                else:
                    bg.paste(img, (paste_x, paste_y))
            else:
                bg.paste(img, (paste_x, paste_y))
            
            bg.save(thumb_path, "JPEG", quality=80)
            return True
    except Exception:
        return False
