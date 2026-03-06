import os
import sys

# ── 베이스 디렉토리 설정 ────────────────────────────────────────────────────────
if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ── 주요 경로 정의 ─────────────────────────────────────────────────────────────
HISTORY_DIR   = os.path.join(BASE_DIR, "history")
CONFIG_FILE   = os.path.join(BASE_DIR, "config.json")
LOCALE_DIR    = os.path.join(BASE_DIR, "locale")
LOG_FILE      = os.path.join(BASE_DIR, "app_debug.log")

# ── 리소스(res) 경로 정의 ───────────────────────────────────────────────────────
RES_DIR       = os.path.join(BASE_DIR, "res")
FONTS_DIR     = os.path.join(RES_DIR, "fonts")
IMAGES_DIR    = os.path.join(RES_DIR, "Images")
SOUNDS_DIR    = os.path.join(RES_DIR, "sounds")

# ── 초기화 ────────────────────────────────────────────────────────────────────
def ensure_directories():
    """필요한 디렉토리가 없으면 생성합니다."""
    for d in [HISTORY_DIR, LOCALE_DIR, RES_DIR, FONTS_DIR, IMAGES_DIR, SOUNDS_DIR]:
        if not os.path.exists(d):
            os.makedirs(d, exist_ok=True)
