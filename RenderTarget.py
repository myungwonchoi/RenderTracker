"""
MW Render Monitor  —  PySide6 (shadcn-inspired dark UI)
"""

import sys
import os
import json
import time
import threading
import requests
import traceback
import discord_utils
import constants
from styles import T, STYLE_SHEET_TEMPLATE
from datetime import datetime

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False

try:
    from PIL import Image
    PILLOW_AVAILABLE = True
except ImportError:
    PILLOW_AVAILABLE = False

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QScrollArea, QFrame, QGridLayout,
    QProgressBar, QTextEdit, QLineEdit, QCheckBox, QRadioButton,
    QDialog, QButtonGroup, QSpacerItem, QSizePolicy, QSizeGrip, QMessageBox,
    QMenu, QSystemTrayIcon
)
from PySide6.QtGui import QFontDatabase, QFont, QPixmap, QIcon, QCursor, QColor, QPainter, QAction, QPainterPath, QImageReader, QLinearGradient, QBrush
from PySide6.QtCore import Qt, QTimer, Signal, QPoint, QSize, QUrl, Property, QPropertyAnimation, QEasingCurve
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput

# ── 경로 ───────────────────────────────────────────────────────────────────────
if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

HISTORY_DIR   = os.path.join(BASE_DIR, "history")
CONFIG_FILE   = os.path.join(BASE_DIR, "config.json")
LOCALE_DIR    = os.path.join(BASE_DIR, "locale")
FONTS_DIR     = os.path.join(BASE_DIR, "res", "fonts")
LOG_FILE      = os.path.join(BASE_DIR, "app_debug.log")

def log_to_file(msg, level="INFO"):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"[{ts}] [{level}] {msg}\n")
    except: pass

def handle_exception(exc_type, exc_value, exc_traceback):
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
    err_msg = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
    log_to_file(f"CRITICAL UNHANDLED EXCEPTION:\n{err_msg}", "CRITICAL")
    sys.__excepthook__(exc_type, exc_value, exc_traceback)

sys.excepthook = handle_exception


# ── 설정·메시지 유틸 ───────────────────────────────────────────────────────────
def load_config():
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def save_config(data):
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False

def load_messages(lang="ko"):
    try:
        path = os.path.join(LOCALE_DIR, f"{lang}.json")
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def fmt_time(s):
    if s is None or s < 0:
        return "—"
    m, s = divmod(int(s), 60)
    h, m = divmod(m, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"

# ── 디스코드 웹훅 연동 (순수 파이썬 유지) ──────────────────────────────────────────

# ── 커스텀 메시지 박스 ────────────────────────────────────────────────────────
class CustomMessageBox(QDialog):
    def __init__(self, parent, title, message):
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setModal(True)
        if parent:
            self.setGeometry(parent.geometry())
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Dimmed background overlay
        overlay = QWidget()
        overlay.setObjectName("DimOverlay")
        overlay.setStyleSheet(f"#DimOverlay {{ background-color: rgba(0, 0, 0, 180); border-radius: 11px; }}")

        overlay_layout = QVBoxLayout(overlay)
        
        self.card = QFrame()
        self.card.setObjectName("Card")
        self.card.setFixedSize(400, 220)
        clayout = QVBoxLayout(self.card)
        clayout.setContentsMargins(0, 0, 0, 0)
        clayout.setSpacing(0)
        
        # Title bar
        title_bar = QWidget()
        title_bar.setObjectName("TitleBar")
        title_bar.setAttribute(Qt.WA_StyledBackground)
        title_bar.setFixedHeight(34)
        tb_layout = QHBoxLayout(title_bar)
        tb_layout.setContentsMargins(12, 0, 12, 0)
        tb_lbl = QLabel(title)
        tb_lbl.setStyleSheet("font-weight: bold; font-size: 12px;")
        tb_layout.addWidget(tb_lbl)
        tb_layout.addStretch()
        close_btn = QPushButton("✕")
        close_btn.setObjectName("CloseBtn")
        close_btn.setFixedSize(40, 34)
        close_btn.clicked.connect(self.reject)
        tb_layout.addWidget(close_btn)
        clayout.addWidget(title_bar)
        
        # Body
        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(24, 20, 24, 24)
        
        body_lbl = QLabel(message)
        body_lbl.setWordWrap(True)
        body_lbl.setStyleSheet(f"color: {T.MUTED2}; font-size: 14px;")
        body_layout.addWidget(body_lbl)
        
        body_layout.addStretch()
        
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        ok_btn = QPushButton("OK")
        ok_btn.setObjectName("PrimaryBtn")
        ok_btn.setFixedWidth(80)
        ok_btn.clicked.connect(self.accept)
        btn_layout.addWidget(ok_btn)
        body_layout.addLayout(btn_layout)
        
        clayout.addWidget(body)
        overlay_layout.addWidget(self.card, 0, Qt.AlignCenter)
        layout.addWidget(overlay)

class GlowCard(QFrame):
    """일반적인 카드 패널 (이후 스타일 변경 용이성을 위해 유지)"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Card")

class MainGlowOverlay(QWidget):
    """메인 패널 전체 영역 내부에 은은한 글로우를 표현하는 오버레이"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WA_NoSystemBackground)
        self._intensity = 0.0
        self._color = QColor(T.GREEN)
        self.hide()

    @Property(float)
    def intensity(self): return self._intensity
    @intensity.setter
    def intensity(self, val):
        self._intensity = val
        self.update()

    def set_glow(self, color_hex):
        self._color = QColor(color_hex)
        self.show()

    def paintEvent(self, event):
        if self._intensity <= 0: return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # 가시성 및 고급스러운 느낌을 주도록 알파값과 범위 조정
        alpha = int(self._intensity * 180) # 강도를 살짝 높임
        c = QColor(self._color)
        c.setAlpha(alpha)
        
        w, h = self.width(), self.height()
        p = T.GLOW_SPREAD
        
        painter.setPen(Qt.NoPen)
        
        # 1. 상단 (Top) - 타이틀바 바로 아래 은은하게
        g_top = QLinearGradient(0, 0, 0, p)
        g_top.setColorAt(0, c); g_top.setColorAt(1, Qt.transparent)
        painter.fillRect(0, 0, w, p, QBrush(g_top))
        
        # 2. 하단 (Bottom)
        g_bot = QLinearGradient(0, h, 0, h - p)
        g_bot.setColorAt(0, c); g_bot.setColorAt(1, Qt.transparent)
        painter.fillRect(0, h - p, w, p, QBrush(g_bot))
        
        # 3. 좌측 (Left)
        g_left = QLinearGradient(0, 0, p, 0)
        g_left.setColorAt(0, c); g_left.setColorAt(1, Qt.transparent)
        painter.fillRect(0, 0, p, h, QBrush(g_left))
        
        # 4. 우측 (Right)
        g_right = QLinearGradient(w, 0, w - p, 0)
        g_right.setColorAt(0, c); g_right.setColorAt(1, Qt.transparent)
        painter.fillRect(w - p, 0, p, h, QBrush(g_right))


# ── 커스텀 위젯 (타이틀 바) ──────────────────────────────────────────────────
class CustomTitleBar(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_window = parent
        self.setObjectName("TitleBar")
        self.setAttribute(Qt.WA_StyledBackground)
        self.setFixedHeight(34)
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 0, 0)
        
        self.title_label = QLabel("MW Render Monitor")
        self.title_label.setStyleSheet(f"color: {T.FG};")
        layout.addWidget(self.title_label)
        layout.addStretch()
        
        self.min_btn = QPushButton("—")
        self.min_btn.setFixedSize(40, 34)
        self.min_btn.clicked.connect(self.parent_window.showMinimized)
        layout.addWidget(self.min_btn)
        
        self.close_btn = QPushButton("✕")
        self.close_btn.setObjectName("CloseBtn")
        self.close_btn.setFixedSize(40, 34)
        self.close_btn.clicked.connect(self.parent_window.close)
        layout.addWidget(self.close_btn)
        
        self.start_pos = None

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            # OS 네이티브 드래그 시작 (멀티 모니터 DPI 대응)
            if self.window().windowHandle():
                self.window().windowHandle().startSystemMove()

    def mouseMoveEvent(self, event):
        # startSystemMove를 사용하므로 수동 계산이 필요 없음
        pass

    def mouseReleaseEvent(self, event):
        # 드래그 로직이 OS로 넘어가므로 상태 관리 불필요
        pass

class HistoryCard(QFrame):
    clicked = Signal(str)
    rightClicked = Signal(str)
    
    def __init__(self, path, label_text, doc_name, sw, status_color, parent=None):
        super().__init__(parent)
        self.path = path
        self.setObjectName("Card")
        self.setCursor(QCursor(Qt.PointingHandCursor))
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        
        title_row = QHBoxLayout()
        self.title_lbl = QLabel(doc_name) # 프로젝트 이름을 메인 제목으로
        self.title_lbl.setStyleSheet(f"color: {T.FG}; font-weight: bold; font-size: 13px; border: none;")
        
        self.status_dot = QWidget()
        self.status_dot.setFixedSize(8, 8)
        self.status_dot.setStyleSheet(f"background-color: {status_color}; border-radius: 4px; border: none;")
        
        title_row.addWidget(self.title_lbl)
        title_row.addStretch()
        title_row.addWidget(self.status_dot)
        layout.addLayout(title_row)
        
        bottom_layout = QHBoxLayout()
        self.date_lbl = QLabel(label_text) # 날짜를 하단 서브 정보로
        self.date_lbl.setStyleSheet(f"color: {T.MUTED}; font-size: 11px; border: none;")
        bottom_layout.addWidget(self.date_lbl)
        bottom_layout.addStretch()
        
        layout.addLayout(bottom_layout)
        self.set_active(False)

    def set_active(self, is_active):
        if is_active:
            self.setStyleSheet(f"#Card {{ background-color: {T.BORDER}; border: 1px solid {T.MUTED}; }}")
        else:
            self.setStyleSheet(f"#Card {{ background-color: {T.CARD}; border: 1px solid transparent; }}")

    def set_status_color(self, color):
        self.status_dot.setStyleSheet(f"background-color: {color}; border-radius: 4px; border: none;")

    def contextMenuEvent(self, event):
        self.rightClicked.emit(self.path)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.path)

class CustomSizeGrip(QWidget):
    """OS 네이티브 리사이즈를 트리거하는 커스텀 그립"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(24, 24)
        self.setCursor(Qt.SizeFDiagCursor)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            handle = self.window().windowHandle()
            if handle:
                # 멀티 모니터 DPI 대응을 위해 OS에 리사이즈 위임
                handle.startSystemResize(Qt.RightEdge | Qt.BottomEdge)

# ── 설정 다이얼로그 ─────────────────────────────────────────────────────────────
class SettingsDialog(QDialog):
    def __init__(self, parent, cfg, msgs, on_change_callback):
        super().__init__(parent)
        self.cfg = dict(cfg)
        self.msgs = msgs
        self.on_change_callback = on_change_callback
        self._ui_elements = {}

        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setModal(True)
        if parent:
            self.setGeometry(parent.geometry())
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Dimmed background overlay
        overlay = QWidget()
        overlay.setObjectName("DimOverlay")
        overlay.setStyleSheet(f"#DimOverlay {{ background-color: rgba(0, 0, 0, 180); border-radius: 11px; }}")
        overlay_layout = QVBoxLayout(overlay)
        
        # 전체 래퍼 (라운딩 적용)
        self.main_card = QFrame()
        self.main_card.setObjectName("Card")
        self.main_card.setFixedSize(500, 680)
        clayout = QVBoxLayout(self.main_card)
        clayout.setContentsMargins(0, 0, 0, 0)
        
        # 언어 헬퍼
        self.m = lambda k, d="": self.msgs.get(f"ui_{k}", self.msgs.get(k, d or k))

        def create_section_lbl(text_key, default):
            lbl = QLabel(self.m(text_key, default))
            lbl.setStyleSheet(f"color: {T.MUTED}; font-weight: bold; font-size: 13px; margin-bottom: 4px;")
            self._ui_elements[f"section_{text_key}"] = (lbl, text_key, default)
            return lbl


        # ── 커스텀 타이틀바 ──
        title_bar = QWidget()
        title_bar.setObjectName("TitleBar")
        title_bar.setAttribute(Qt.WA_StyledBackground)
        title_bar.setFixedHeight(34)
        tb_layout = QHBoxLayout(title_bar)
        tb_layout.setContentsMargins(12, 0, 0, 0)
        
        self.title_bar_lbl = QLabel(self.m("settings", "Settings"))
        self.title_bar_lbl.setStyleSheet("font-weight: bold;")
        tb_layout.addWidget(self.title_bar_lbl)
        tb_layout.addStretch()
        
        close_btn = QPushButton("✕")
        close_btn.setObjectName("CloseBtn")
        close_btn.setFixedSize(40, 34)
        close_btn.clicked.connect(self.reject)
        tb_layout.addWidget(close_btn)
        
        clayout.addWidget(title_bar)

        # ── 메인 바디 ──
        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(20, 20, 20, 20)
        
        # 언어 설정 섹션
        body_layout.addWidget(create_section_lbl("app_lang", "Language"))
        lang_card = QFrame(); lang_card.setObjectName("Card")
        lang_layout = QGridLayout(lang_card)
        lang_layout.setContentsMargins(20, 20, 20, 20)
        lang_layout.setVerticalSpacing(20)
        lang_layout.setHorizontalSpacing(16)
        
        self.lbl_app_lang = QLabel(self.m("app_lang", "App Language"))
        self.lbl_app_lang.setStyleSheet(f"color: {T.MUTED2}; font-size: 13px;")
        lang_layout.addWidget(self.lbl_app_lang, 0, 0)
        self.bg_app_lang = QButtonGroup(self)
        self.rb_app_en = QRadioButton("English")
        self.rb_app_ko = QRadioButton("Korean")
        self.bg_app_lang.addButton(self.rb_app_en, 1)
        self.bg_app_lang.addButton(self.rb_app_ko, 2)
        if self.cfg.get("app_language", "ko") == "en": self.rb_app_en.setChecked(True)
        else: self.rb_app_ko.setChecked(True)
        lang_box = QHBoxLayout(); lang_box.addWidget(self.rb_app_en); lang_box.addWidget(self.rb_app_ko)
        lang_layout.addLayout(lang_box, 0, 1)

        self.lbl_disc_lang = QLabel(self.m("discord_lang", "Discord Language"))
        self.lbl_disc_lang.setStyleSheet(f"color: {T.MUTED2}; font-size: 13px;")
        lang_layout.addWidget(self.lbl_disc_lang, 1, 0)
        self.bg_disc_lang = QButtonGroup(self)
        self.rb_disc_en = QRadioButton("English")
        self.rb_disc_ko = QRadioButton("Korean")
        self.bg_disc_lang.addButton(self.rb_disc_en, 1)
        self.bg_disc_lang.addButton(self.rb_disc_ko, 2)
        if self.cfg.get("language", "ko") == "en": self.rb_disc_en.setChecked(True)
        else: self.rb_disc_ko.setChecked(True)
        disc_box = QHBoxLayout(); disc_box.addWidget(self.rb_disc_en); disc_box.addWidget(self.rb_disc_ko)
        lang_layout.addLayout(disc_box, 1, 1)
        body_layout.addWidget(lang_card)

        
        body_layout.addSpacing(10)
        
        # Webhook 설정 섹션
        body_layout.addWidget(create_section_lbl("webhook_section", "Discord Webhook"))
        wh_card = QFrame(); wh_card.setObjectName("Card")
        wh_layout = QGridLayout(wh_card)
        wh_layout.setContentsMargins(20, 20, 20, 20)
        wh_layout.setVerticalSpacing(16)
        wh_layout.setHorizontalSpacing(16)
        wh_layout.setColumnStretch(1, 1)
        
        self.lbl_wh_url = QLabel(self.m("webhook_url", "Webhook URL"))
        self.lbl_wh_url.setStyleSheet(f"color: {T.MUTED2}; font-size: 13px;")
        wh_layout.addWidget(self.lbl_wh_url, 0, 0)
        self.le_wh_url = QLineEdit(self.cfg.get("webhook_url", ""))
        wh_layout.addWidget(self.le_wh_url, 0, 1)
        
        self.lbl_mention = QLabel(self.m("use_mention", "@Mention"))
        self.lbl_mention.setStyleSheet(f"color: {T.MUTED2}; font-size: 13px;")
        wh_layout.addWidget(self.lbl_mention, 1, 0)
        self.chk_mention = QCheckBox()
        self.chk_mention.setChecked(self.cfg.get("use_mention", False))
        wh_layout.addWidget(self.chk_mention, 1, 1)
        
        self.lbl_uid = QLabel(self.m("discord_userid", "Discord User ID"))
        self.lbl_uid.setStyleSheet(f"color: {T.MUTED2}; font-size: 13px;")
        wh_layout.addWidget(self.lbl_uid, 2, 0)
        self.le_wh_uid = QLineEdit(self.cfg.get("discord_userid", ""))
        wh_layout.addWidget(self.le_wh_uid, 2, 1)
        
        self.lbl_pc_name = QLabel(self.m("pc_name", "PC Name"))
        self.lbl_pc_name.setStyleSheet(f"color: {T.MUTED2}; font-size: 13px;")
        wh_layout.addWidget(self.lbl_pc_name, 3, 0)
        self.le_pc_name = QLineEdit(self.cfg.get("pc_name", ""))
        wh_layout.addWidget(self.le_pc_name, 3, 1)
        
        body_layout.addWidget(wh_card)

        
        body_layout.addSpacing(10)
        
        # 사운드 설정 섹션
        body_layout.addWidget(create_section_lbl("sound_settings", "Sound Notifications"))
        snd_card = QFrame(); snd_card.setObjectName("Card")
        snd_layout = QGridLayout(snd_card)
        snd_layout.setContentsMargins(20, 20, 20, 20)
        snd_layout.setVerticalSpacing(16)
        snd_layout.setHorizontalSpacing(16)
        
        self.lbl_volume = QLabel(self.m("volume", "Volume"))
        self.lbl_volume.setStyleSheet(f"color: {T.MUTED2}; font-size: 13px;")
        snd_layout.addWidget(self.lbl_volume, 0, 0)
        from PySide6.QtWidgets import QSlider
        self.sl_volume = QSlider(Qt.Horizontal)
        self.sl_volume.setRange(0, 100)
        self.sl_volume.setValue(self.cfg.get("volume", 50))
        snd_layout.addWidget(self.sl_volume, 0, 1)
        
        body_layout.addWidget(snd_card)

        body_layout.addStretch()
        
        # 하단 버튼
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        self.save_btn = QPushButton(self.m("close", "Save & Close"))
        self.save_btn.setObjectName("SecondaryBtn")
        self.save_btn.clicked.connect(self._save_and_close)
        btn_layout.addWidget(self.save_btn)
        body_layout.addLayout(btn_layout)
        
        clayout.addWidget(body)
        overlay_layout.addWidget(self.main_card, 0, Qt.AlignCenter)
        layout.addWidget(overlay)
        
        self.chk_mention.toggled.connect(self._update_uid_state)
        self.rb_app_en.toggled.connect(self._on_app_lang_toggled)
        self.rb_app_ko.toggled.connect(self._on_app_lang_toggled)
        self._update_uid_state()

    def _on_app_lang_toggled(self):
        if self.sender().isChecked():
            # 즉시 저장 및 반영
            self.cfg["app_language"] = "en" if self.rb_app_en.isChecked() else "ko"
            if save_config(self.cfg):
                # 부모의 msgs 등을 갱신하기 위해 callback 호출
                self.on_change_callback(self.cfg)
                # 현재 다이얼로그의 m 도 갱신하려면 self.msgs를 바꿔야 함
                self.msgs = load_messages(self.cfg["app_language"])
                self._apply_dialog_lang()

    def _apply_dialog_lang(self):
        self.m = lambda k, d="": self.msgs.get(f"ui_{k}", self.msgs.get(k, d or k))
        
        self.title_bar_lbl.setText(self.m("settings", "Settings"))
        self.lbl_app_lang.setText(self.m("app_lang", "App Language"))
        self.lbl_disc_lang.setText(self.m("discord_lang", "Discord Language"))
        self.lbl_wh_url.setText(self.m("webhook_url", "Webhook URL"))
        self.lbl_mention.setText(self.m("use_mention", "@Mention"))
        self.lbl_uid.setText(self.m("discord_userid", "Discord User ID"))
        self.lbl_pc_name.setText(self.m("pc_name", "PC Name"))
        self.lbl_volume.setText(self.m("volume", "Volume"))
        self.save_btn.setText(self.m("close", "Save & Close"))

        for key, (lbl, text_key, default) in self._ui_elements.items():
            if key.startswith("section_"):
                lbl.setText(self.m(text_key, default))

    def _update_uid_state(self):
        is_men = self.chk_mention.isChecked()
        self.le_wh_uid.setEnabled(is_men)
        self.lbl_uid.setStyleSheet(f"color: {T.MUTED2 if is_men else T.MUTED}; font-size: 13px;")


    def _save_and_close(self):
        self.cfg["app_language"] = "en" if self.rb_app_en.isChecked() else "ko"
        self.cfg["language"] = "en" if self.rb_disc_en.isChecked() else "ko"
        self.cfg["webhook_url"] = self.le_wh_url.text().strip()
        self.cfg["discord_userid"] = self.le_wh_uid.text().strip()
        self.cfg["use_mention"] = self.chk_mention.isChecked()
        self.cfg["pc_name"] = self.le_pc_name.text().strip()
        self.cfg["volume"] = self.sl_volume.value()
        
        if save_config(self.cfg):
            self.on_change_callback(self.cfg)
        self.accept()

# ── 메인 윈도우 앱 ─────────────────────────────────────────────────────────────
class RenderMonitorApp(QMainWindow):
    def __init__(self):
        super().__init__()
        # 윈도우 플래그 보완 (작업 표시줄 표시 및 프레임리스 설정)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Window | Qt.WindowMinMaxButtonsHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_StaticContents, True) # 리사이즈 시 깜빡임 차단 최적화
        self.resize(920, 950)
        self.setMinimumSize(600, 600)
        self.setMaximumHeight(1080)
        
        # Windows 11 라운드 코너 적용
        self._setup_native_window()
        
        # 설정 로드
        self.cfg = load_config()
        
        # 창 위치 및 크기 복원 (저장된 정보가 있으면 복원, 없으면 중앙 정렬)
        geom = self.cfg.get("window_geometry")
        if geom:
            try:
                self.restoreGeometry(bytes.fromhex(geom))
            except:
                self._center_window()
        else:
            self._center_window()
        self._app_lang = self.cfg.get("app_language", "ko")
        self.app_msgs = load_messages(self._app_lang)
        self.msgs = load_messages(self.cfg.get("language", "ko"))
        
        self.start_app_ts = time.time()
        self.last_start_ts = None
        self.last_status = None
        self.last_rendered_frames = -1
        self.progress_msg_id = None
        self.watched_pid = None
        self.crash_sent = False
        self.last_init = {}
        self.last_upd = {}
        
        self._active_file = None
        self._viewing_file = None
        self._history_btns = {}
        self._history_mtimes = {}
        self._first_img_path = None
        self._first_img_mtime = 0
        self._last_img_path = None
        self._last_img_mtime = 0
        # Audio
        self.audio_output = QAudioOutput()
        self.player = QMediaPlayer()
        self.player.setAudioOutput(self.audio_output)
        self.is_muted = (self.cfg.get("volume", 50) == 0)
        self.last_non_zero_volume = self.cfg.get("volume", 50) if not self.is_muted else 50
        self._update_volume()
        
        # [Fix] 시작 시 기존 히스토리를 데이터로만 로드 (알림/소리 방지)
        latest = self._get_latest_render_file()
        if latest:
            try:
                with open(latest, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.last_start_ts = data.get("start", {}).get("start_ts")
                    self._active_file = latest
                    # 초기 데이터 로드 (Silent)
                    self._process(data, from_history=True) 
            except: pass
        
        # 시스템 트레이 아이콘 설정
        self._setup_tray_icon()
        
        self._build_ui()
        self._apply_lang()
        
        self._log("Monitor started (PySide6)")
        self._log(f"Watching: {HISTORY_DIR}")
        
        self.poll_timer = QTimer(self)
        self.poll_timer.timeout.connect(self._poll)
        self.poll_timer.start(constants.POLLING_INTERVAL_MS)

        # Glow Overlay (창 전체 은은하게 빛나기)
        self.glow_overlay = MainGlowOverlay(self)
        self.glow_overlay.setGeometry(0, 34, self.width(), self.height() - 34)
        self.glow_overlay.lower() 

        self._glow_anim = None

    def _setup_native_window(self):
        """Windows 11 네이티브 라운드 코너 적용"""
        if sys.platform == "win32":
            import ctypes
            from ctypes import wintypes
            
            hwnd = self.winId()
            DWMWA_WINDOW_CORNER_PREFERENCE = 33
            DWMWCP_ROUND = 2
            
            dwmapi = ctypes.windll.dwmapi
            dwmapi.DwmSetWindowAttribute(
                wintypes.HWND(hwnd),
                DWMWA_WINDOW_CORNER_PREFERENCE,
                ctypes.byref(ctypes.c_int(DWMWCP_ROUND)),
                ctypes.sizeof(ctypes.c_int)
            )

    def _center_window(self):
        qr = self.frameGeometry()
        cp = self.screen().availableGeometry().center()
        qr.moveCenter(cp)
        self.move(qr.topLeft())

    def _build_ui(self):
        central = QWidget()
        central.setObjectName("MainBackground")
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # 타이틀 바
        self.title_bar = CustomTitleBar(self)
        main_layout.addWidget(self.title_bar)
        
        # 컨텐츠 영역
        content = QWidget()
        content_layout = QHBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)
        
        # ── 사이드바 ──
        self.sidebar_wrap = QWidget()
        self.sidebar_wrap.setFixedWidth(220)
        sidebar_layout = QVBoxLayout(self.sidebar_wrap)
        sidebar_layout.setContentsMargins(12, 12, 0, 12)
        
        self.sb_hdr_lbl = QLabel("렌더 기록")
        self.sb_hdr_lbl.setStyleSheet(f"color: {T.MUTED}; font-weight: bold; font-size: 14px;")
        sidebar_layout.addWidget(self.sb_hdr_lbl)
        
        self.sidebar_scroll = QScrollArea()
        self.sidebar_scroll.setWidgetResizable(True)
        self.sidebar_content = QWidget()
        self.sidebar_layout_inner = QVBoxLayout(self.sidebar_content)
        self.sidebar_layout_inner.setContentsMargins(0, 0, 8, 0)
        self.sidebar_layout_inner.setSpacing(4)
        self.sidebar_layout_inner.addStretch() # Top-align items
        self.sidebar_scroll.setWidget(self.sidebar_content)
        sidebar_layout.addWidget(self.sidebar_scroll)
        
        content_layout.addWidget(self.sidebar_wrap)
        
        self.sep = QFrame()
        self.sep.setFrameShape(QFrame.VLine)
        self.sep.setStyleSheet(f"color: {T.BORDER};")
        content_layout.addWidget(self.sep)
        
        # ── 메인 뷰 (우측) ──
        self.right_scroll = QScrollArea()
        self.right_scroll.setWidgetResizable(True)
        right_content = QWidget()
        self.right_layout = QVBoxLayout(right_content)
        self.right_layout.setContentsMargins(20, 20, 20, 20)
        self.right_layout.setSpacing(16)
        
        # 헤더 카드
        hdr_widget = QWidget()
        hdr_layout = QHBoxLayout(hdr_widget)
        hdr_layout.setContentsMargins(0,0,0,0)
        
        left_hdr = QVBoxLayout()
        self.app_title_lbl = QLabel("—")
        self.app_title_lbl.setStyleSheet(f"font-size: 20px; font-weight: bold; color: {T.FG};")

        left_hdr.addWidget(self.app_title_lbl)
        
        self.status_badge = QLabel("")
        self.status_badge.setStyleSheet(f"background-color: {T.BADGE_YELLOW}; color: {T.YELLOW}; font-weight: bold; padding: 4px 8px; border-radius: 4px;")
        self.status_badge.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Preferred)
        left_hdr.addWidget(self.status_badge)
        hdr_layout.addLayout(left_hdr)
        
        right_hdr = QVBoxLayout()
        right_hdr.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.pid_label = QLabel("PID: —")
        self.pid_label.setStyleSheet(f"color: {T.MUTED};")
        right_hdr.addWidget(self.pid_label, alignment=Qt.AlignRight)
        
        btn_box = QHBoxLayout()
        btn_box.setSpacing(6)
        
        self.volume_btn = QPushButton()
        self.volume_btn.setObjectName("VolumeBtn")
        self.volume_btn.clicked.connect(self._toggle_mute)
        
        self.settings_btn = QPushButton()
        self.settings_btn.setObjectName("SettingsBtn")
        
        # 아이콘 설정
        icon_path = os.path.join(BASE_DIR, "res", "Images", "Icon_Setting.png")
        if os.path.exists(icon_path):
            self.settings_btn.setIcon(QIcon(icon_path))
            self.settings_btn.setIconSize(QSize(20, 20))
        else:
            self.settings_btn.setText("⚙")

        # 볼륨 아이콘 (시스템 폰트 또는 텍스트)
        self.volume_btn.setText("🔊")
        self.volume_btn.setStyleSheet("font-size: 16px;")
            
        self.settings_btn.clicked.connect(self._open_settings)
        
        btn_box.addWidget(self.volume_btn)
        btn_box.addWidget(self.settings_btn)
        right_hdr.addLayout(btn_box)
        hdr_layout.addLayout(right_hdr)
        self.right_layout.addWidget(hdr_widget)
        
        # 프로그레스 카드
        self.prog_card = GlowCard()
        prog_layout = QVBoxLayout(self.prog_card)
        prog_layout.setContentsMargins(20, 20, 20, 20)
        
        # 이미지 컨테이너 (First Frame | Last Frame)
        self.img_container = QWidget()
        self.img_container.hide()
        self.img_layout = QHBoxLayout(self.img_container)
        self.img_layout.setContentsMargins(0, 0, 0, 0)
        self.img_container.show() # 항상 표시하여 레이아웃 고정
        prog_layout.addWidget(self.img_container)
        
        self.first_img_label = QLabel("No Image")
        self.first_img_label.setAlignment(Qt.AlignCenter)
        self.first_img_label.setFixedSize(240, 135)
        self.first_img_label.setStyleSheet(f"border: 1px solid {T.BORDER}; border-radius: 12px; background: {T.BG}; color: {T.MUTED};")
        self.img_layout.addWidget(self.first_img_label)
        
        self.last_img_label = QLabel("No Image")
        self.last_img_label.setAlignment(Qt.AlignCenter)
        self.last_img_label.setFixedSize(240, 135)
        self.last_img_label.setStyleSheet(f"border: 1px solid {T.BORDER}; border-radius: 12px; background: {T.BG}; color: {T.MUTED};")
        self.img_layout.addWidget(self.last_img_label)
        
        pb_top = QHBoxLayout()
        self.prog_hdr_lbl = QLabel("Progress")
        self.prog_hdr_lbl.setStyleSheet(f"color: {T.MUTED}; font-weight: bold;")
        self.pct_label = QLabel("0.0%")
        self.pct_label.setStyleSheet("font-weight: bold;")
        pb_top.addWidget(self.prog_hdr_lbl); pb_top.addStretch(); pb_top.addWidget(self.pct_label)
        prog_layout.addLayout(pb_top)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedHeight(8)
        self.progress_bar.setRange(0, 1000)
        self.progress_bar.setValue(0)
        prog_layout.addWidget(self.progress_bar)
        
        pb_bot = QHBoxLayout()
        self.start_f_label = QLabel("— F"); self.start_f_label.setStyleSheet(f"color: {T.MUTED};")
        self.curr_f_prog_label = QLabel("—F"); self.curr_f_prog_label.setStyleSheet("font-weight: bold;")
        self.end_f_label = QLabel("— F"); self.end_f_label.setStyleSheet(f"color: {T.MUTED};")
        pb_bot.addWidget(self.start_f_label); pb_bot.addStretch(); pb_bot.addWidget(self.curr_f_prog_label); pb_bot.addStretch(); pb_bot.addWidget(self.end_f_label)
        prog_layout.addLayout(pb_bot)
        self.right_layout.addWidget(self.prog_card)
        
        # 렌더 정보 카드
        self._card_labels = {}
        self._info_vars = {}
        self.info_card = GlowCard()
        info_layout = QGridLayout(self.info_card)
        info_layout.setContentsMargins(20, 20, 20, 20)
        info_layout.setVerticalSpacing(8)
        info_layout.setHorizontalSpacing(4)
        info_layout.setColumnStretch(1, 1) # 두 번째 컬럼(값)이 너비를 가득 채우고 유동적으로 조절되도록 설정
        
        card_keys = ["software","renderer","doc","render_set","take","resolution",
                     "frame_range","start_time","end_time","total_elapsed","output_path"]
        for i, key in enumerate(card_keys):
            lbl = QLabel("")
            lbl.setStyleSheet(f"color: {T.MUTED}; font-size: 13px;") 
            lbl.setFixedWidth(110) # 100 -> 110으로 약간 상향 (한글 가독성)
            lbl.setAlignment(Qt.AlignTop | Qt.AlignLeft)
            
            val = QLabel("—")
            val.setWordWrap(True)
            val.setMinimumSize(50, 0) # 더 작게까지 줄어들 수 있도록 허용
            val.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
            val.setAlignment(Qt.AlignTop | Qt.AlignLeft)
            val.setTextInteractionFlags(Qt.TextSelectableByMouse)
            
            if key == "output_path":
                val.setCursor(QCursor(Qt.PointingHandCursor))
                val.setStyleSheet(f"color: {T.BLUE}; text-decoration: underline;")
                val.mousePressEvent = lambda e: self._open_output_folder()
            
            self._card_labels[key] = lbl
            self._info_vars[key] = val
            info_layout.addWidget(lbl, i, 0)
            info_layout.addWidget(val, i, 1)
        self.right_layout.addWidget(self.info_card)
        
        # 진행 상세 카드 (그리드)
        self.prog_detail_card = GlowCard()
        detail_layout = QGridLayout(self.prog_detail_card)
        detail_layout.setContentsMargins(20, 20, 20, 20)
        detail_layout.setVerticalSpacing(20)   # 행 간 간격 (항목 간)
        detail_layout.setHorizontalSpacing(16) # 열 간 간격
        
        self._prog_labels = {}
        LAYOUT = [
            ("current_frame_time", 0, 0), ("last_frame", 0, 1), ("avg_frame", 0, 2),
            ("elapsed", 1, 0), ("remaining", 1, 1), ("eta", 1, 2)
        ]
        for key, r, c in LAYOUT:
            v_box = QVBoxLayout()
            v_box.setSpacing(2) # 간격을 다시 2px로 복구
            
            lbl = QLabel(""); lbl.setStyleSheet(f"color: {T.MUTED}; font-size: 13px;") # 11px -> 13px
            val = QLabel("—"); val.setStyleSheet("font-size: 15px; font-weight: 500;")
            
            self._prog_labels[key] = lbl
            self._info_vars[key] = val
            v_box.addWidget(lbl)
            v_box.addWidget(val)
            detail_layout.addLayout(v_box, r, c)
        self.right_layout.addWidget(self.prog_detail_card)
        
        # 로그 헤더 레이아웃
        log_hdr_layout = QHBoxLayout()
        self._log_section_lbl = QLabel("Log")
        self._log_section_lbl.setStyleSheet(f"color: {T.MUTED}; font-weight: bold;")
        log_hdr_layout.addWidget(self._log_section_lbl)
        log_hdr_layout.addStretch()
        
        self.right_layout.addLayout(log_hdr_layout)
        
        self.log_container = GlowCard()
        log_inner_layout = QVBoxLayout(self.log_container)
        log_inner_layout.setContentsMargins(12, 12, 12, 12)
        
        self.log_text = QTextEdit()
        self.log_text.setMinimumHeight(120)
        self.log_text.setReadOnly(True)
        self.log_text.setStyleSheet("font-size: 10px; line-height: 120%;")
        log_inner_layout.addWidget(self.log_text)
        
        self.right_layout.addWidget(self.log_container)
        
        self.right_layout.addStretch() # 하단 여백 복원
        self.right_scroll.setWidget(right_content)
        content_layout.addWidget(self.right_scroll, 1) # flex=1
        
        main_layout.addWidget(content)
        
        # 창 크기 조절 그립 (우측 하단)
        self.size_grip_wrap = QWidget(self)
        self.size_grip_wrap.setFixedSize(32, 32)
        sg_layout = QVBoxLayout(self.size_grip_wrap)
        sg_layout.setContentsMargins(0, 0, 4, 4) 
        sg_layout.setSpacing(0)
        
        # 커스텀 네이티브 리사이즈 그립 사용
        size_grip = CustomSizeGrip(self)
        sg_layout.addWidget(size_grip, 0, Qt.AlignBottom | Qt.AlignRight)
        
        # 윈도우 크기 최대 세로 길이 제한 (하단 영역까지만 확장 가능)
    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'size_grip_wrap'):
            # 창 구석에서 32px 위치로 고정 (라운드 모서리 안쪽)
            self.size_grip_wrap.move(self.width() - 32, self.height() - 32)
            
        # [Optimization] 글로우 오버레이가 보일 때만 리사이즈 처리하여 깜빡임(Flicker) 감소
        if hasattr(self, 'glow_overlay') and not self.glow_overlay.isHidden():
            self.glow_overlay.move(0, 34)
            self.glow_overlay.resize(self.width(), self.height() - 34)

    def closeEvent(self, event):
        """창을 닫을 때 종료되지 않고 시스템 트레이로 숨김"""
        # 창 위치/크기 저장
        self.cfg["window_geometry"] = self.saveGeometry().toHex().data().decode()
        save_config(self.cfg)
        
        # 이미 트레이 아이콘이 보이고 있다면 창만 숨기고 종료 차단
        if self.tray_icon.isVisible():
            self.hide()
            event.ignore() # 종료 방지
            self._log("Minimized to system tray")
        else:
            # 트레이 오류 등으로 안 보일 경우에만 실제 종료
            event.accept()

    def _setup_tray_icon(self):
        """시스템 트레이 아이콘 및 메뉴 구성"""
        self.tray_icon = QSystemTrayIcon(self)
        
        # 아이콘 설정 (기존 설정 아이콘 활용)
        icon_path = os.path.join(BASE_DIR, "res", "Images", "Icon_Setting.png")
        if os.path.exists(icon_path):
            self.tray_icon.setIcon(QIcon(icon_path))
        
        # 우클릭 메뉴
        tray_menu = QMenu()
        
        show_action = QAction(self.g("ui_show", "Show"), self)
        show_action.triggered.connect(self._activate_main_window)
        tray_menu.addAction(show_action)
        
        tray_menu.addSeparator()
        
        quit_action = QAction(self.g("ui_exit", "Exit"), self)
        quit_action.triggered.connect(self._actual_quit)
        tray_menu.addAction(quit_action)
        
        self.tray_icon.setContextMenu(tray_menu)
        
        # 트레이 아이콘 클릭 시 행동
        self.tray_icon.activated.connect(self._on_tray_activated)
        self.tray_icon.show()

    def _on_tray_activated(self, reason):
        """트레이 아이콘 클릭/더블클릭 시 창 띄움"""
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleTrigger):
            if self.isVisible():
                self.hide()
            else:
                self._activate_main_window()

    def _actual_quit(self):
        """앱을 완전히 종료"""
        self.tray_icon.hide()
        QApplication.quit()

    def _set_status(self, key, fg, bg):
        txt = self.g(key)
        # 텍스트와 스타일(배경색으로 판단)이 모두 같으면 업데이트 생략하여 깜빡임 방지
        if self.status_badge.text() == txt and self.status_badge.property("status_key") == key:
            return
        self.status_badge.setText(txt)
        self.status_badge.setProperty("status_key", key)
        self.status_badge.setStyleSheet(f"background-color: {bg}; color: {fg}; font-weight: bold; padding: 4px 8px; border-radius: 4px;")

    def _iv(self, key, val):
        if key in self._info_vars:
            new_txt = str(val)
            if self._info_vars[key].text() == new_txt:
                return
            self._info_vars[key].setText(new_txt)

    def _set_bar(self, pct, color):
        val = int(pct * 1000)
        self.progress_bar.setValue(val)
        self.pct_label.setText(f"{pct * 100:.1f}%")
        self.progress_bar.setStyleSheet(f"""
            QProgressBar {{ background-color: {T.BORDER}; border: none; border-radius: 4px; text-align: right; color: transparent; }}
            QProgressBar::chunk {{ background-color: {color}; border-radius: 4px; }}
        """)

    def g(self, key, default=""):
        return self.app_msgs.get(f"ui_{key}", self.app_msgs.get(key, default or key))

    def _apply_lang(self):
        # 최상단 타이틀바 고정 (메인 프로젝트명 라벨은 데이터에 따라 관리되므로 여기선 건드리지 않음)
        self.title_bar.title_label.setText("MW Render Monitor")
        
        self.prog_hdr_lbl.setText(self.g("progress_label", "Progress"))

        self.sb_hdr_lbl.setText(self.g("history", "Render History"))
        
        # 볼륨 아이콘 업데이트
        if self.is_muted:
            self.volume_btn.setText("🔇")
        else:
            self.volume_btn.setText("🔊")
        
        pid_text = self.g("pid", "PID")
        cur_pid = (self.watched_pid if self.watched_pid else "—")
        self.pid_label.setText(f"{pid_text}: {cur_pid}")
        
        MAP = {
            "software": "ui_software", "renderer": "ui_renderer", "doc": "ui_doc", "render_set": "ui_render_set",
            "take": "ui_take", "resolution": "ui_resolution", "frame_range": "ui_frame_range",
            "start_time": "ui_start_time", "end_time": "ui_end_time", 
            "total_elapsed": "ui_elapsed", "output_path": "ui_output_path"
        }
        for key, lbl in self._card_labels.items():
            lbl.setText(self.app_msgs.get(MAP.get(key, f"ui_{key}"), key))
            
        PROG_MAP = {
            "current_frame_time": "field_current_frame_time", "last_frame": "ui_last_frame",
            "avg_frame": "ui_avg_frame", "elapsed": "ui_elapsed",
            "remaining": "ui_remaining", "eta": "ui_eta"
        }
        for key, lbl in self._prog_labels.items():
            lbl.setText(self.app_msgs.get(PROG_MAP.get(key, f"ui_{key}"), key))
            
        self._log_section_lbl.setText(self.g("log", "Log"))
        self.open_log_btn = None # Removed
        self.open_history_btn = None # Removed
        
        if self.last_status:
            key_map = {
                "Progress": "progress", 
                "Started": "started", 
                "Finished": "finished", 
                "Stopped": "stopped", 
                "Crashed": "crashed",
                "NotResponding": "not_responding",
                "SoftwareClosed": "software_closed"
            }
            badge_key = key_map.get(self.last_status, self.last_status.lower())
            self.status_badge.setText(self.g(badge_key, self.last_status))

    def _log(self, msg, level="INFO"):
        ts = time.strftime("%H:%M:%S")
        line = f"[{ts}] {msg}"
        print(line)
        log_to_file(msg, level)
        self.log_text.append(line)
        scrollbar = self.log_text.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def _trigger_glow(self, color_hex):
        """창 전체 글로우 효과를 트리거하고 애니메이션을 수행합니다."""
        if not hasattr(self, "glow_overlay"):
            return
            
        self.glow_overlay.set_glow(color_hex)
        self.glow_overlay.resize(self.width(), self.height() - 34) # 트리거 시 크기 재조정 (안전장치)
        self.glow_overlay.raise_() 
        
        if self._glow_anim:
            self._glow_anim.stop()
            
        self._glow_anim = QPropertyAnimation(self.glow_overlay, b"intensity")
        
        # 상수를 이용한 타이밍 계산
        total_ms = T.GLOW_PEAK_MS + T.GLOW_EXIT_MS
        peak_at = T.GLOW_PEAK_MS / total_ms
        
        self._glow_anim.setDuration(total_ms)
        self._glow_anim.setStartValue(0.0)
        self._glow_anim.setKeyValueAt(peak_at, T.GLOW_INTENSITY) # 목표 강도 도달
        self._glow_anim.setEndValue(0.0)                         # 서서히 소멸
        self._glow_anim.setEasingCurve(QEasingCurve.OutCubic)
        self._glow_anim.start()

    def _open_settings(self):
        dlg = SettingsDialog(self, self.cfg, self.app_msgs, self._on_cfg_changed)
        dlg.exec()

    def _on_cfg_changed(self, new_cfg):
        prev_lang = self._app_lang
        self.cfg = new_cfg
        self.msgs = load_messages(new_cfg.get("language","ko"))
        self._app_lang = new_cfg.get("app_language","ko")
        self.app_msgs = load_messages(self._app_lang)
        if self._app_lang != prev_lang:
            self._apply_lang()
        self._update_volume()
        self._log("Settings updated")

    def _open_output_folder(self):
        folder = self._info_vars["output_path"].text().replace("\u200b", "")
        if folder and folder != "—":
            if os.path.exists(folder):
                os.startfile(folder)
            else:
                msg = self.g("path_not_found", "The folder path does not exist.")
                dlg = CustomMessageBox(self, self.g("app_title"), msg)
                dlg.exec()

    # ── 히스토리 및 폴링 로직 ────────────────────────────────────────────────────────
    def _get_latest_render_file(self):
        if not os.path.isdir(HISTORY_DIR): return None
        # 파일명을 알파벳순(시간순)으로 정렬하여 가장 최근 것 선택 (성능 최적화)
        files = [f for f in os.listdir(HISTORY_DIR) if f.startswith("Render_") and f.endswith(".json")]
        if not files: return None
        files.sort(reverse=True)
        return os.path.join(HISTORY_DIR, files[0])

    def _refresh_sidebar(self):
        if not os.path.isdir(HISTORY_DIR): return
        # 파일명 정렬 (성능을 위해 getmtime 배제)
        files = sorted(
            [os.path.join(HISTORY_DIR, f) for f in os.listdir(HISTORY_DIR) if f.startswith("Render_") and f.endswith(".json")],
            reverse=True
        )
        
        current_paths = set(files)
        known_paths = set(self._history_btns.keys())
        
        # 1. 삭제된 파일 위젯 제거
        removed_paths = known_paths - current_paths
        for p in removed_paths:
            btn = self._history_btns.pop(p, None)
            if btn: btn.deleteLater()
            self._history_mtimes.pop(p, None)

        # 2. 추가된 파일 위젯 생성
        added_paths = current_paths - known_paths
        if added_paths:
            # 순서를 유지하기 위해 정렬된 리스트에서 새로 추가된 것만 추출
            # reversed(files)를 사용하는 이유는 insertWidget(0)이 역순으로 쌓기 때문입니다.
            for path in reversed(files):
                if path in added_paths:
                    # 레이아웃 상단에 추가해야 함 (insertWidget)
                    self._add_to_sidebar(path, top=True)
        
        # 3. 기존 파일 내용 변경 체크 (상태 색상 등)
        for path in files:
            if path in known_paths:
                try:
                    mt = os.path.getmtime(path)
                    if mt != self._history_mtimes.get(path, 0):
                        self._history_mtimes[path] = mt
                        color = self._get_status_color_from_file(path)
                        if path in self._history_btns:
                            self._history_btns[path].set_status_color(color)
                except: pass
            
        self._highlight_sidebar(self._viewing_file or self._active_file)

    def _get_status_color_from_file(self, path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            info = data.get("start", {})
            upd = data.get("update", {})
            end = data.get("end", {})
            end_ts = end.get("end_ts", -1)
            ren = upd.get("rendered_frames", 0)
            tot = info.get("total_frames", 0)
            if end_ts <= 0: return T.YELLOW
            if ren >= tot > 0: return T.GREEN
            return T.RED
        except: return T.RED

    def _add_to_sidebar(self, path, top=False):
        doc_name = "Unknown"
        sw = "C4D"
        status_color = T.RED
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._history_mtimes[path] = os.path.getmtime(path)
            info = data.get("start", {})
            doc_name = info.get("doc_name", "Unknown")
            sw = info.get("software", "C4D")
            status_color = self._get_status_color_from_file(path)
        except: pass

        try:
            basename = os.path.basename(path)
            date_part = basename[len("Render_"):-len(".json")]
            dt = time.strptime(date_part, "%Y%m%d_%H%M%S")
            label = time.strftime("%Y-%m-%d %H:%M:%S", dt)
        except: label = os.path.basename(path)
        
        card = HistoryCard(path, label, doc_name, sw, status_color)
        card.clicked.connect(self._load_history)
        card.rightClicked.connect(self._show_history_context_menu)
        
        if top:
            # 레이아웃의 맨 위에 추가 (인덱스 0)
            self.sidebar_layout_inner.insertWidget(0, card)
        else:
            # 기존 방식: 스페이서 바로 위에 추가
            self.sidebar_layout_inner.insertWidget(self.sidebar_layout_inner.count() - 1, card)
            
        self._history_btns[path] = card
        self._highlight_sidebar(self._viewing_file or self._active_file)

    def _highlight_sidebar(self, active_path):
        for path, card in self._history_btns.items():
            card.set_active(path == active_path)

    def _load_history(self, path):
        self._viewing_file = path
        self._highlight_sidebar(path)
        
        # [Fix] 항목 변경 시 즉시 이미지를 지우지 않고, _process에서 로드 결과에 따라 처리 (유지 후 대체)
        self._first_img_path = None
        self._last_img_path = None
        self._first_img_mtime = 0
        self._last_img_mtime = 0
        
        if not os.path.exists(path):
            self._log(f"[History] File not found: {os.path.basename(path)}")
            self.first_img_label.setText("No Image")
            self.last_img_label.setText("No Image")
            return
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            self._process(data, from_history=True)
        except Exception as e:
            self._log(f"[History] {e}")

    def _show_history_context_menu(self, path):
        menu = QMenu(self)
        
        remove_act = QAction(self.g("remove_record", "Remove Record"), self)
        remove_act.triggered.connect(lambda: self._remove_history_item(path))
        
        clear_all_act = QAction(self.g("clear_all_history", "Clear All History"), self)
        clear_all_act.triggered.connect(self._clear_all_history)
        
        menu.addAction(remove_act)
        menu.addSeparator()
        menu.addAction(clear_all_act)
        
        menu.exec(QCursor.pos())

    def _remove_history_item(self, path):
        try:
            # 원본 JSON 삭제
            if os.path.exists(path):
                os.remove(path)
                
            # 관련 이미지 삭제
            for suffix in ["_LastFrame.jpg", "_LastFrameTemp.jpg", "_FirstFrame.jpg", "_FirstFrameTemp.jpg"]:
                img_p = path.replace(".json", suffix)
                if os.path.exists(img_p): os.remove(img_p)
            
            self._log(f"Removed history: {os.path.basename(path)}")
            
            # 현재 보고 있는 파일이 삭제된 거라면 메인 뷰 초기화
            if self._viewing_file == path or self._active_file == path:
                self._viewing_file = None
                if self._active_file == path: self._active_file = None
                self._reset_main_view()

            self._refresh_sidebar()
        except Exception as e:
            self._log(f"Error removing history: {e}")

    def _clear_all_history(self):
        msg = "Are you sure you want to delete ALL render history?"
        if self._app_lang == "ko":
            msg = "정말 모든 렌더 기록을 삭제하시겠습니까?"
            
        dlg = CustomMessageBox(self, self.g("ui_history"), msg)
        if dlg.exec():
            try:
                for f in os.listdir(HISTORY_DIR):
                    if f.startswith("Render_") and (f.endswith(".json") or f.endswith(".jpg")):
                        os.remove(os.path.join(HISTORY_DIR, f))
                self._log("Cleared all history")
                self._viewing_file = None
                self._active_file = None
                self._reset_main_view()
                self._refresh_sidebar()
            except Exception as e:
                self._log(f"Error clearing history: {e}")

    def _reset_main_view(self):
        """메인 뷰의 정보들을 초기화(비움)"""
        for key in self._info_vars:
            self._iv(key, "—")
        self.app_title_lbl.setText("—")


        self.status_badge.setText("")
        self.pct_label.setText("0.0%")
        self.progress_bar.setValue(0)
        self.img_container.show()
        self.first_img_label.setPixmap(QPixmap())
        self.first_img_label.setText("No Image")
        self.last_img_label.setPixmap(QPixmap())
        self.last_img_label.setText("No Image")
        self._first_img_path = None
        self._last_img_path = None
        self.watched_pid = None
        self.pid_label.setText(f"{self.g('pid', 'PID')}: —")

    def _poll(self):
        try:
            self._refresh_sidebar()
            
            # 1. 프로세스 생존 여부 실시간 체크 (꺼졌다면 정지/종료로 판단)
            if self.watched_pid and self.last_status == "Progress":
                if PSUTIL_AVAILABLE:
                    try:
                        p = psutil.Process(self.watched_pid)
                        if not p.is_running() or p.status() == psutil.STATUS_ZOMBIE:
                            self._log(f"Process {self.watched_pid} is no longer running.")
                            self._on_crash()
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        self._log(f"Process {self.watched_pid} not found. Assuming closed.")
                        self._on_crash()

            latest = self._get_latest_render_file()
            if latest:
                if latest != self._active_file:
                    self._active_file = latest
                    self._viewing_file = None
                    self._highlight_sidebar(latest)
                    self._log(f"New render detected: {os.path.basename(latest)}")

                target = self._viewing_file if self._viewing_file else self._active_file
                if target:
                    # 파일 수정 시간 체크 (응답 없음 감지용)
                    mtime = os.path.getmtime(target)
                    now = time.time()
                    
                    with open(target, "r", encoding="utf-8") as fh:
                        data = json.load(fh)
                    
                    # 2. 응답 없음 감지 (파일 업데이트가 평균 시간의 3배 이상 지연될 때)
                    upd = data.get("update", {})
                    avg = upd.get("avg_frame_duration", 10.0) # 기본 10초
                    timeout_threshold = max(avg * 3, 120.0)    # 최소 2분
                    
                    is_progress = (data.get("end", {}).get("end_ts", -1) <= 0)
                    if is_progress and (now - mtime > timeout_threshold) and not self._viewing_file:
                        if self.last_status != "NotResponding":
                            self._log(f"Render update delayed ({int(now-mtime)}s). Potential hang.", "WARNING")
                            self.last_status = "NotResponding"
                            # _process 이전에 먼저 상태를 설정 (이후 _process에서 override 방지 로직 필요)
                            self._set_status("not_responding", T.ORANGE, T.BADGE_RED)
                    
                    self._process(data, from_history=(target != self._active_file))
        except Exception as e:
            pass

    def _mask_rounded_pixmap(self, pixmap, radius=12):
        if pixmap.isNull(): return pixmap
        size = pixmap.size()
        rounded = QPixmap(size)
        rounded.fill(Qt.transparent)
        
        from PySide6.QtGui import QPainter, QPainterPath, QPen, QColor
        from PySide6.QtCore import QRectF
        painter = QPainter(rounded)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        
        # 라운딩 마스크 (이미지가 둥글게 잘리도록)
        path = QPainterPath()
        path.addRoundedRect(QRectF(0, 0, size.width(), size.height()), radius, radius)
        painter.setClipPath(path)
        painter.drawPixmap(0, 0, pixmap)
        
        # 테두리 그리기 (UI 스타일의 1px 테두리와 완전히 일치하도록 수학적 보정)
        painter.setClipping(False)
        pen = QPen(QColor(T.BORDER))
        pen.setWidth(1)
        painter.setPen(pen)
        # 1px 두께 선이 정확히 안쪽 경계에 위치하도록 0.5 오프셋 사용 및 곡률 축소
        painter.drawRoundedRect(QRectF(0.5, 0.5, size.width() - 1, size.height() - 1), radius - 0.5, radius - 0.5)
        
        painter.end()
        return rounded

    def _process(self, data, from_history=False):
        init = data.get("start",  {})
        upd  = data.get("update", {})
        end  = data.get("end",    {})

        # 1. 기초 데이터 추출
        start_ts = init.get("start_ts")
        end_ts   = end.get("end_ts", -1)
        ren      = upd.get("rendered_frames", 0)
        tot      = init.get("total_frames", 1)
        curr_f   = upd.get("current_frame", 0)
        pid      = init.get("c4d_pid")
        sw       = init.get("software", "—")
        is_ended = (end_ts is not None and end_ts > 0)
        
        # 2. 알림/신호 발생 조건 선판단 (복잡한 if 방지)
        is_realtime = not from_history
        is_new      = (start_ts is not None and start_ts != self.last_start_ts)
        # "앱 실행 이후에 일어난 일인가?"
        is_fresh_start = (is_realtime and start_ts and start_ts > self.start_app_ts)
        is_fresh_end   = (is_realtime and end_ts and end_ts > self.start_app_ts)

        self.last_init = init
        self.last_upd  = upd

        # 3. PID 감시 (프로세스 추적)
        if pid and pid != self.watched_pid:
            self.watched_pid = pid
            self.crash_sent  = False
            self.pid_label.setText(f"{self.g('pid', 'PID')}: {pid}")
            self._log(f"PID: {pid}")
            if PSUTIL_AVAILABLE:
                threading.Thread(target=self._watch_pid, args=(pid,), daemon=True).start()

        # 4. 새로운 렌더링 세션 시작 처리
        if is_new:
            self.last_start_ts        = start_ts
            self.progress_msg_id      = None
            self.crash_sent           = False
            self.last_status          = None
            self.last_rendered_frames = -1
            self._last_thumb_update_ts = 0
            self._last_thumb_frame_num = -1
            
            # [Fix] 히스토리 조회 시에는 끊김 없는 전환을 위해 이미지를 유지하지만,
            # 실시간으로 새로운 렌더링이 감지된 경우에는 이전 흔적을 지우기 위해 화면을 비움
            self._first_img_path = None
            self._last_img_path = None
            self._first_img_mtime = 0
            self._last_img_mtime = 0
            
            # 실시간 모니터링 중 새로운 세션이 감지된 경우에만 썸네일 영역 초기화
            if is_realtime:
                self.first_img_label.setPixmap(QPixmap()); self.first_img_label.setText("No Image")
                self.last_img_label.setPixmap(QPixmap());  self.last_img_label.setText("No Image")

            
            self._set_status("started", T.GREEN, T.BADGE_GREEN)
            # 실시간 새 렌더링이면 알림 발생
            if is_fresh_start:
                self._log(f"New render detected (TS: {start_ts})")
                threading.Thread(target=self._do_started, args=(dict(init),), daemon=True).start()
                self._play_render_sound("Start")
                self._activate_main_window()
                QApplication.alert(self, 0)
                # 시작 글로우 (파란색)
                self._trigger_glow(T.BLUE)
            self._set_status("started", T.GREEN, T.BADGE_GREEN)
            
            # [Fix] 실시간으로 새로운 렌더링이 시작될 때만 양쪽 패널 모두 최상단으로 스크롤
            if not from_history:
                self._scroll_to_top(sidebar=True)



        # 5. 상태 결정 (Progress / Finished / Stopped)
        if not is_ended:
            status = "Progress"
        elif ren >= tot > 0:
            status = "Finished"
        else:
            status = "Stopped"

        # 6. UI 업데이트 (항상 실행)
        self._iv("software", sw)
        self._iv("renderer", init.get("renderer", "—"))
        
        doc_name = init.get("doc_name", "")
        self._iv("doc", doc_name if doc_name else "—")
        if doc_name:
            self.app_title_lbl.setText(doc_name)
        else:
            self.app_title_lbl.setText("—")


        
        is_blender = (sw.upper() == "BLENDER")
        for key in ["render_set", "take"]:
            if key in self._card_labels:
                self._card_labels[key].setVisible(not is_blender)
                self._info_vars[key].setVisible(not is_blender)

        if not is_blender:
            self._iv("render_set", init.get("render_setting", "—"))
            self._iv("take",       init.get("take_name", "—"))
        
        self._iv("resolution",  f"{init.get('res_x',0)} × {init.get('res_y',0)}")
        self._iv("frame_range", f"{init.get('start_frame',0)} – {init.get('end_frame',0)}  ({tot} frames)")
        self._iv("start_time",  init.get("start_time","—"))
        
        path = init.get("output_path","")
        self._iv("output_path", path.replace("\\", "\\\u200b").replace("/", "/\u200b") if path else "—")
        
        self._iv("current_frame_time", upd.get("field_current_frame_time", "—"))
        self._iv("last_frame",         fmt_time(upd.get("last_frame_duration", 0)))
        self._iv("avg_frame",          fmt_time(upd.get("avg_frame_duration", 0)))
        self._iv("elapsed",            fmt_time(upd.get("elapsed_seconds", 0)))
        self.start_f_label.setText(f"{init.get('start_frame','—')} F")
        self.end_f_label.setText(f"{init.get('end_frame','—')} F")
        self.curr_f_prog_label.setText(f"{upd.get('current_frame',0)}F")

        # 7. 상태별 신호 발송 로직 (리팩토링됨)
        pct = ren / tot if tot > 0 else 0.0
        
        if status == "Progress":
            # [Fix] 외부에서 이미 '응답 없음'으로 판단된 경우, 단순히 '진행 중'으로 덮어쓰지 않음
            if self.last_status == "NotResponding" and not from_history:
                # 상태 뱃지의 텍스트는 유지하고 진행바 등만 업데이트하도록 설정 유지
                pass 
            else:
                self.last_status = "Progress"
                rem = upd.get("remaining_seconds", -1)
                self._iv("remaining", fmt_time(rem) if rem >= 0 else "—")
                self._iv("eta", time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(time.time()+rem)) if rem >= 0 else "—")
                self._iv("end_time", "—")
                self._iv("total_elapsed", fmt_time(upd.get("elapsed_seconds", 0)))
                self._set_status("progress", T.YELLOW, T.BADGE_YELLOW)
            self._set_bar(pct, T.YELLOW)

            # 진행 상황이 변했고, 실시간 모드인 경우에만 디스코드 업데이트
            if not is_new and ren != self.last_rendered_frames:
                self.last_rendered_frames = ren
                if is_realtime:
                    threading.Thread(target=self._do_progress, args=(dict(init), dict(upd), self.progress_msg_id, self._last_img_path), daemon=True).start()

        elif status in ("Finished", "Stopped"):
            # 이전 상태와 다를 때만 로그 및 처리
            if self.last_status != status:
                if is_realtime: self._log(f"→ {status}")
                self.last_status = status
                
                # UI 데이터 갱신
                self._iv("current_frame_time", self._info_vars["last_frame"].text())
                self._iv("remaining", "—")
                self._iv("eta", "—")
                self._iv("end_time", end.get("end_time","—"))
                self._iv("total_elapsed", fmt_time(upd.get("elapsed_seconds", 0)))
                
                is_fin = (status == "Finished")
                self._set_status(status.lower(), (T.GREEN if is_fin else T.RED), (T.BADGE_GREEN if is_fin else T.BADGE_RED))
                self._set_bar(pct, (T.GREEN if is_fin else T.RED))
                
                # [Fix] 실시간으로 렌더가 종료/중단되었을 때만 스크롤 초기화
                if not from_history:
                    self._scroll_to_top(sidebar=True)


                # [실시간 알림 및 효과] 앱 실행 이후에 발생한 신규 이벤트인 경우에만 실행
                if is_realtime and is_fresh_end:
                    # 글로우 효과
                    self._trigger_glow(T.GREEN if is_fin else T.RED)
                    # 외부 알림 및 소리
                    threading.Thread(target=self._do_finished, args=(dict(init), dict(upd), dict(end), is_fin, self._last_img_path), daemon=True).start()
                    self._play_render_sound("End" if is_fin else "Error")
                    self._activate_main_window()
                    QApplication.alert(self, 0)
        else:
            pass

        # 8. 썸네일 업데이트 (앱에서 직접 복사 및 리사이징 처리)
        # 중요: 렌더 중 실시간 경로는 init 대신 upd에서 가져와야 최신화됩니다.
        curr_path = upd.get("current_frame_path")
        if curr_path:
            init["last_frame_path"] = curr_path

        now_ts = time.time()
        base_configs = [
            {
                "key": "first_frame_path",
                "path_attr": "_first_img_path",
                "mtime_attr": "_first_img_mtime",
                "label": self.first_img_label,
                "suffix": "_FirstFrame.jpg",
                "throttle": False
            },
            {
                "key": "last_frame_path",
                "path_attr": "_last_img_path",
                "mtime_attr": "_last_img_mtime",
                "label": self.last_img_label,
                "suffix": "_LastFrame.jpg",
                "throttle": True
            }
        ]

        # JSON 파일명을 기반으로 저장될 썸네일 이름 결정
        json_basename = os.path.basename(self._viewing_file or self._active_file)
        
        for cfg in base_configs:
            raw_source = init.get(cfg["key"])
            if not raw_source:
                # [Fix] 소스 경로가 없을 경우에만 No Image 표시
                cfg["label"].setPixmap(QPixmap())
                cfg["label"].setText("No Image")
                continue


            # 1. 원본 파일 존재 확인 및 보편적 포맷 체크
            actual_source = None
            SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tga"}
            
            # 원본 경로 확인
            if os.path.exists(raw_source):
                actual_source = raw_source
            else:
                # 확장자가 없거나 틀릴 경우를 대비해 지원되는 확장자들만 시도
                _base, _ext = os.path.splitext(raw_source)
                for test_ext in SUPPORTED_EXTENSIONS:
                    test_p = _base + test_ext
                    if os.path.exists(test_p):
                        actual_source = test_p
                        break
            
            if not actual_source:
                # [Fix] 실제 파일이 없을 경우에만 No Image 표시
                cfg["label"].setPixmap(QPixmap())
                cfg["label"].setText("No Image")
                continue


            _ext = os.path.splitext(actual_source)[1].lower()
            if _ext not in SUPPORTED_EXTENSIONS:
                # 지원되지 않는 포맷일 경우에만 No Image 표시
                cfg["label"].setPixmap(QPixmap())
                cfg["label"].setText("No Image")
                continue


            thumb_path = os.path.join(HISTORY_DIR, json_basename.replace(".json", cfg["suffix"]))
            
            # 3초 스로틀 체크 (Last Frame 용)
            if cfg["throttle"] and not from_history:
                last_time = getattr(self, "_last_thumb_update_ts", 0)
                last_f_num = getattr(self, "_last_thumb_frame_num", -1)
                
                # 프레임이 바뀌지 않았으면 굳이 업데이트 안 함 (3초가 지났더라도)
                if curr_f == last_f_num: 
                    continue 
                # 프레임은 바뀌었어도 1.0초가 안 지났으면 스킵
                if now_ts - last_time < 1.0: 
                    continue

            # 업데이트 필요 여부 판단
            processed_key = f"{cfg['key']}_processed"
            needs_update = False
            if not os.path.exists(thumb_path):
                needs_update = True
            elif not from_history: 
                # 렌더링 중일 때는 소스 경로가 바뀌었는지 체크
                if actual_source != getattr(self, processed_key, None):
                    needs_update = True

            if needs_update:
                try:
                    # [Optimization] Pillow의 draft()와 thumbnail()을 같이 사용하여 가장 가볍게 불러옴
                    with Image.open(actual_source) as img:
                        target_size = (240, 135)
                        
                        # 1단계: JPEG 전용 드래프트 최적화 (로딩 전 스케일 결정)
                        if actual_source.lower().endswith((".jpg", ".jpeg")):
                            img.draft(img.mode, target_size)
                        
                        # 2단계: 최단 시간 보간법(NEAREST)으로 썸네일 생성 및 복사
                        img.thumbnail(target_size, resample=Image.Resampling.NEAREST)
                        
                        # [Fix] 3단계: 16:9 패딩 배경은 검은색, 알파가 있는 영역에만 투명 패턴 표시
                        bg_size = (240, 135)
                        bg = Image.new("RGB", bg_size, (11, 11, 11))
                        
                        paste_x = (bg_size[0] - img.width) // 2
                        paste_y = (bg_size[1] - img.height) // 2
                        
                        is_transparent = (img.mode in ("RGBA", "P"))
                        if is_transparent:
                            # 투명 배경 이미지 로드 (BG_Transparent.png)
                            bg_path = os.path.join(BASE_DIR, "res", "Images", "BG_Transparent.png")
                            if os.path.exists(bg_path):
                                try:
                                    with Image.open(bg_path) as bg_img:
                                        pattern = bg_img.convert("RGB").resize(bg_size, Image.Resampling.NEAREST)
                                        img_bg = pattern.crop((paste_x, paste_y, paste_x + img.width, paste_y + img.height))
                                except:
                                    img_bg = Image.new("RGB", img.size, (11, 11, 11))
                            else:
                                img_bg = Image.new("RGB", img.size, (11, 11, 11))
                                
                            if img.mode == "RGBA":
                                img_bg.paste(img, mask=img.split()[3])
                            else:
                                img_bg.paste(img)
                                
                            bg.paste(img_bg, (paste_x, paste_y))
                        else:
                            bg.paste(img, (paste_x, paste_y))
                            
                        save_img = bg

                        # 4단계: 로컬 history 폴더에 저장 (이미지 복사 효과)
                        save_img.save(thumb_path, "JPEG", quality=80)
                        
                        # 화면 표시용 Pixmap 변환
                        pix = QPixmap(thumb_path)
                        if not pix.isNull():
                            masked_pix = self._mask_rounded_pixmap(pix, radius=12)
                            cfg["label"].setPixmap(masked_pix)
                            cfg["label"].setText("")
                        
                        # 상태 기록
                        setattr(self, cfg["path_attr"], thumb_path)
                        setattr(self, processed_key, actual_source)
                        if cfg["throttle"]:
                            self._last_thumb_update_ts = now_ts
                            self._last_thumb_frame_num = curr_f
                            self._log(f"Thumbnail updated: Frame {curr_f}")
                except Exception as e:
                    self._log(f"Thumbnail error: {e}", "WARNING")
                    cfg["label"].setPixmap(QPixmap())
                    cfg["label"].setText("No Image")

            else:
                # 이미 처리된 파일이 있는 경우 화면 로딩
                current_shown = getattr(self, cfg["path_attr"], None)
                if not current_shown or current_shown != thumb_path:
                    pix = QPixmap(thumb_path)
                    if not pix.isNull():
                        masked_pix = self._mask_rounded_pixmap(pix, radius=12)
                        cfg["label"].setPixmap(masked_pix)
                        cfg["label"].setText("")
                        setattr(self, cfg["path_attr"], thumb_path)
                    else:
                        # 썸네일 파일 로드 실패(손상 등) 시 No Image
                        cfg["label"].setPixmap(QPixmap())
                        cfg["label"].setText("No Image")


    def _watch_pid(self, pid):
        try: psutil.Process(pid).wait()
        except: pass
        finally:
            if self.last_status not in ("Finished","Stopped") and not self.crash_sent:
                self.crash_sent = True
                QTimer.singleShot(0, self._on_crash) # 메인 스레드에서 실행

    def _on_crash(self):
        self._log("C4D process ended (Crash or Closed)")
        self.last_status = "Crashed"
        
        # JSON 강제 업데이트 (밀봉): 프로세스가 죽었으나 JSON에 종료 기록이 없는 경우 보정
        target = self._active_file
        if target and os.path.exists(target):
            try:
                with open(target, "r", encoding="utf-8") as f:
                    data = json.load(f)
                
                # end_ts가 -1이거나 없으면 현재 시간으로 강제 기입
                end_info = data.get("end", {})
                if end_info.get("end_ts", -1) <= 0:
                    now_ts = time.time()
                    data["end"] = {
                        "end_ts": now_ts,
                        "end_time": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(now_ts))
                    }
                    with open(target, "w", encoding="utf-8") as f:
                        json.dump(data, f, ensure_ascii=False, indent=2)
                    self._log(f"Force updated JSON on process end: {os.path.basename(target)}")
            except Exception as e:
                self._log(f"Failed to force update JSON: {e}")

        self._set_status("crashed", T.RED, T.BADGE_RED)
        self._trigger_glow(T.RED)
        self._set_bar(self.progress_bar.value() / 1000.0, T.RED)
        self._play_render_sound("Error")
        self._activate_main_window()
        self._scroll_to_top()
        threading.Thread(target=discord_utils.notify_crash, args=(self.last_init, self.last_upd, self.cfg, self.msgs), daemon=True).start()

    def _do_started(self, init):
        mid = discord_utils.notify_started(init, self.cfg, self.msgs)
        if mid: self._log("Started Discord notified")

    def _do_progress(self, init, upd, captured, thumb_path=None):
        new_id = discord_utils.notify_progress(init, upd, self.cfg, self.msgs, captured, thumb_path=thumb_path)
        if new_id and new_id != captured:
            self.progress_msg_id = new_id

    def _do_finished(self, init, upd, end, is_fin, thumb_path=None):
        discord_utils.notify_finished(init, upd, end, self.cfg, self.msgs, is_fin, pmid=self.progress_msg_id, thumb_path=thumb_path)

    def _update_volume(self):
        vol = self.cfg.get("volume", 50)
        self.is_muted = (vol == 0)
        if not self.is_muted:
            self.last_non_zero_volume = vol
        self.audio_output.setVolume(vol / 100.0)
        
        # 버튼 아이콘 즉시 반영
        if hasattr(self, 'volume_btn'):
            self.volume_btn.setText("🔇" if self.is_muted else "🔊")

    def _toggle_mute(self):
        if self.is_muted:
            new_vol = self.last_non_zero_volume
        else:
            self.last_non_zero_volume = self.cfg.get("volume", 50)
            new_vol = 0
            
        self.cfg["volume"] = new_vol
        save_config(self.cfg)
        self._update_volume()
        self._log(f"Volume: {'Muted' if self.is_muted else f'{new_vol}%'}")

    def _play_render_sound(self, sound_type):
        sound_dir = os.path.join(BASE_DIR, "res", "sounds")
        s_path = os.path.join(sound_dir, f"{sound_type}.mp3")
        if os.path.exists(s_path):
            self.player.setSource(QUrl.fromLocalFile(s_path))
            self.player.play()

    def _activate_main_window(self):
        """윈도우 순정 애니메이션(작업표시줄에서 솟아오르는 효과)을 강제 트리거"""
        # [Fix] 이미 활성 창이고 가려지지 않은 상태라면 깜빡임 방지를 위해 애니메이션 스킵
        if self.isActiveWindow() and not self.isMinimized():
            return

        if self.isMinimized():
            self.showNormal()
            self.activateWindow()
        else:
            # 창이 떠있으나 활성화가 안 된 경우 등에는 순정 애니메이션 유도
            self.showMinimized()
            QTimer.singleShot(50, self.showNormal)
            QTimer.singleShot(50, self.activateWindow)


    def _scroll_to_top(self, sidebar=True):
        """사이드바와 메인 UI 스크롤을 최상단으로 이동하지만, sidebar 인자로 제어 가능"""
        if sidebar:
            self.sidebar_scroll.verticalScrollBar().setValue(0)
            # 위젯 추가 직후에는 스크롤 바 범위가 갱신되지 않을 수 있으므로 한 번 더 보정
            QTimer.singleShot(100, lambda: self.sidebar_scroll.verticalScrollBar().setValue(0))
        
        self.right_scroll.verticalScrollBar().setValue(0)
        QTimer.singleShot(100, lambda: self.right_scroll.verticalScrollBar().setValue(0))



if __name__ == "__main__":
    # 고해상도 DPI 및 안티앨리어싱 설정
    if sys.platform == "win32":
        import ctypes
        try:
            # Per Monitor V2 DPI Awareness (가장 선명함)
            ctypes.windll.user32.SetProcessDpiAwarenessContext(-4)
        except:
            try: ctypes.windll.shcore.SetProcessDpiAwareness(1)
            except: pass

    os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "1"
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    
    app = QApplication(sys.argv)
    
    # OS 호환 QFontDatabase로 Pretendard 폰트 로딩
    fonts_loaded = False
    for fname in ["Pretendard-Regular.otf", "Pretendard-Medium.otf", "Pretendard-SemiBold.otf", "Pretendard-Bold.otf",
                  "Pretendard-Regular.ttf", "Pretendard-Medium.ttf", "Pretendard-SemiBold.ttf", "Pretendard-Bold.ttf"]:
        path = os.path.join(FONTS_DIR, fname)
        if os.path.exists(path):
            if QFontDatabase.addApplicationFont(path) != -1:
                fonts_loaded = True
            
    target_font = "Pretendard" if fonts_loaded else "Segoe UI"
    app_font = QFont(target_font, 12)
    
    # [핵심] 렌더링 엔진 설정 조정: 서브픽셀 렌더링 끄기 (NoSubpixelAntialias) 및 힌팅 무시
    # 어두운 배경에서 서브픽셀 렌더링은 글자색을 오염시키고 픽셀을 뭉개는 주범입니다.
    app_font.setStyleStrategy(QFont.PreferAntialias | QFont.PreferQuality | QFont.ForceOutline | QFont.NoSubpixelAntialias)
    app_font.setHintingPreference(QFont.PreferNoHinting) # 원본 폰트 디자인 곡선을 최대로 살림
    app.setFont(app_font)
        
    # 스타일 시트에 최종 폰트 주입
    final_style = STYLE_SHEET_TEMPLATE.replace("{FONT_FAMILY}", f"'{target_font}', 'Segoe UI', sans-serif")
    app.setStyleSheet(final_style)
    
    window = RenderMonitorApp()
    window.show()
    window.raise_()
    window.activateWindow()
    
    sys.exit(app.exec())