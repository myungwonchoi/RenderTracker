import json
import os
from utils.path_manager import CONFIG_FILE, LOCALE_DIR

def load_config():
    """config.json 파일을 로드합니다."""
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {}

def save_config(data):
    """데이터를 config.json 파일로 저장합니다."""
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False

def load_messages(lang="ko"):
    """locale 폴더에서 해당 언어의 JSON 파일을 로드합니다."""
    try:
        path = os.path.join(LOCALE_DIR, f"{lang}.json")
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {}
