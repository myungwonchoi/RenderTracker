import os
import time
import json
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QFrame, QDialog, QButtonGroup, QRadioButton, QCheckBox, 
    QLineEdit, QGridLayout, QSlider, QScrollArea, QSizePolicy, QTextEdit,
    QProgressBar
)
from PySide6.QtGui import QColor, QPainter, QCursor, QLinearGradient, QBrush, QIcon, QPainterPath, QPen, QPixmap
from PySide6.QtCore import Qt, Signal, Property, QSize, QRectF, QPropertyAnimation, QEasingCurve
from ui.styles import T
from utils.config_manager import save_config, load_messages
from utils.path_manager import IMAGES_DIR

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

def mask_rounded_pixmap(pixmap, radius=12):
    """이미지를 둥근 모서리와 테두리가 있는 Pixmap으로 변환합니다."""
    if pixmap.isNull(): return pixmap
    size = pixmap.size()
    rounded = QPixmap(size)
    rounded.fill(Qt.transparent)
    
    painter = QPainter(rounded)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setRenderHint(QPainter.SmoothPixmapTransform)
    
    path = QPainterPath()
    path.addRoundedRect(QRectF(0, 0, size.width(), size.height()), radius, radius)
    painter.setClipPath(path)
    painter.drawPixmap(0, 0, pixmap)
    
    painter.setClipping(False)
    pen = QPen(QColor(T.BORDER))
    pen.setWidth(1)
    painter.setPen(pen)
    painter.drawRoundedRect(QRectF(0.5, 0.5, size.width() - 1, size.height() - 1), radius - 0.5, radius - 0.5)
    
    painter.end()
    return rounded

def trigger_glow_anim(target_widget, anim_attr, color_hex):
    """위젯에 글로우 애니메이션을 트리거합니다."""
    if not target_widget: return None
    
    target_widget.set_glow(color_hex)
    anim = QPropertyAnimation(target_widget, anim_attr.encode() if isinstance(anim_attr, str) else anim_attr)
    
    total_ms = T.GLOW_PEAK_MS + T.GLOW_EXIT_MS
    peak_at = T.GLOW_PEAK_MS / total_ms
    
    anim.setDuration(total_ms)
    anim.setStartValue(0.0)
    anim.setKeyValueAt(peak_at, T.GLOW_INTENSITY)
    anim.setEndValue(0.0)
    anim.setEasingCurve(QEasingCurve.OutCubic)
    anim.start()
    return anim

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

# ── 인터페이스 빌더 ───────────────────────────────────────────────────────────
def build_main_ui(app):
    """메인 윈도우의 전체 레이아웃을 구성합니다."""
    central = QWidget()
    central.setObjectName("MainBackground")
    app.setCentralWidget(central)
    main_layout = QVBoxLayout(central)
    main_layout.setContentsMargins(0, 0, 0, 0)
    main_layout.setSpacing(0)
    
    # 타이틀 바
    app.title_bar = CustomTitleBar(app)
    main_layout.addWidget(app.title_bar)
    
    # 컨텐츠 영역
    content = QWidget()
    content_layout = QHBoxLayout(content)
    content_layout.setContentsMargins(0, 0, 0, 0)
    content_layout.setSpacing(0)
    
    # ── 사이드바 ──
    app.sidebar_wrap = QWidget()
    app.sidebar_wrap.setFixedWidth(220)
    sidebar_layout = QVBoxLayout(app.sidebar_wrap)
    sidebar_layout.setContentsMargins(12, 12, 0, 12)
    
    app.sb_hdr_lbl = QLabel("렌더 기록")
    app.sb_hdr_lbl.setStyleSheet(f"color: {T.MUTED}; font-weight: bold; font-size: 14px;")
    sidebar_layout.addWidget(app.sb_hdr_lbl)
    
    app.sidebar_scroll = QScrollArea()
    app.sidebar_scroll.setWidgetResizable(True)
    app.sidebar_content = QWidget()
    app.sidebar_layout_inner = QVBoxLayout(app.sidebar_content)
    app.sidebar_layout_inner.setContentsMargins(0, 0, 8, 0)
    app.sidebar_layout_inner.setSpacing(4)
    app.sidebar_layout_inner.addStretch()
    app.sidebar_scroll.setWidget(app.sidebar_content)
    sidebar_layout.addWidget(app.sidebar_scroll)
    
    content_layout.addWidget(app.sidebar_wrap)
    
    app.sep = QFrame()
    app.sep.setFrameShape(QFrame.VLine)
    app.sep.setStyleSheet(f"color: {T.BORDER};")
    content_layout.addWidget(app.sep)
    
    # ── 메인 뷰 (우측) ──
    app.right_scroll = QScrollArea()
    app.right_scroll.setWidgetResizable(True)
    right_content = QWidget()
    app.right_layout = QVBoxLayout(right_content)
    app.right_layout.setContentsMargins(20, 20, 20, 20)
    app.right_layout.setSpacing(16)
    
    # 헤더 카드
    hdr_widget = QWidget()
    hdr_layout = QHBoxLayout(hdr_widget)
    hdr_layout.setContentsMargins(0,0,0,0)
    
    left_hdr = QVBoxLayout()
    app.app_title_lbl = QLabel("—")
    app.app_title_lbl.setStyleSheet(f"font-size: 20px; font-weight: bold; color: {T.FG};")
    left_hdr.addWidget(app.app_title_lbl)
    
    app.status_badge = QLabel("")
    app.status_badge.setStyleSheet(f"background-color: {T.BADGE_YELLOW}; color: {T.YELLOW}; font-weight: bold; padding: 4px 8px; border-radius: 4px;")
    app.status_badge.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Preferred)
    left_hdr.addWidget(app.status_badge)
    hdr_layout.addLayout(left_hdr)
    
    right_hdr = QVBoxLayout()
    right_hdr.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
    app.pid_label = QLabel("PID: —")
    app.pid_label.setStyleSheet(f"color: {T.MUTED};")
    right_hdr.addWidget(app.pid_label, alignment=Qt.AlignRight)
    
    btn_box = QHBoxLayout()
    btn_box.setSpacing(6)
    
    app.volume_btn = QPushButton()
    app.volume_btn.setObjectName("VolumeBtn")
    app.settings_btn = QPushButton()
    app.settings_btn.setObjectName("SettingsBtn")
    
    icon_path = os.path.join(IMAGES_DIR, "Icon_Setting.png")
    if os.path.exists(icon_path):
        app.settings_btn.setIcon(QIcon(icon_path))
        app.settings_btn.setIconSize(QSize(20, 20))
    else:
        app.settings_btn.setText("⚙")

    app.volume_btn.setText("🔊")
    app.volume_btn.setStyleSheet("font-size: 16px;")
    
    btn_box.addWidget(app.volume_btn)
    btn_box.addWidget(app.settings_btn)
    right_hdr.addLayout(btn_box)
    hdr_layout.addLayout(right_hdr)
    app.right_layout.addWidget(hdr_widget)
    
    # 프로그레스 카드
    app.prog_card = GlowCard()
    prog_layout = QVBoxLayout(app.prog_card)
    prog_layout.setContentsMargins(20, 20, 20, 20)
    
    app.img_container = QWidget()
    app.img_layout = QHBoxLayout(app.img_container)
    app.img_layout.setContentsMargins(0, 0, 0, 0)
    prog_layout.addWidget(app.img_container)
    
    app.first_img_label = QLabel("No Image")
    app.first_img_label.setAlignment(Qt.AlignCenter)
    app.first_img_label.setFixedSize(240, 135)
    app.first_img_label.setStyleSheet(f"border: 1px solid {T.BORDER}; border-radius: 12px; background: {T.BG}; color: {T.MUTED};")
    app.img_layout.addWidget(app.first_img_label)
    
    app.last_img_label = QLabel("No Image")
    app.last_img_label.setAlignment(Qt.AlignCenter)
    app.last_img_label.setFixedSize(240, 135)
    app.last_img_label.setStyleSheet(f"border: 1px solid {T.BORDER}; border-radius: 12px; background: {T.BG}; color: {T.MUTED};")
    app.img_layout.addWidget(app.last_img_label)
    
    pb_top = QHBoxLayout()
    app.prog_hdr_lbl = QLabel("Progress")
    app.prog_hdr_lbl.setStyleSheet(f"color: {T.MUTED}; font-weight: bold;")
    app.pct_label = QLabel("0.0%")
    app.pct_label.setStyleSheet("font-weight: bold;")
    pb_top.addWidget(app.prog_hdr_lbl); pb_top.addStretch(); pb_top.addWidget(app.pct_label)
    prog_layout.addLayout(pb_top)
    
    app.progress_bar = QProgressBar()
    app.progress_bar.setFixedHeight(8)
    app.progress_bar.setRange(0, 1000)
    app.progress_bar.setValue(0)
    prog_layout.addWidget(app.progress_bar)
    
    pb_bot = QHBoxLayout()
    app.start_f_label = QLabel("— F"); app.start_f_label.setStyleSheet(f"color: {T.MUTED};")
    app.curr_f_prog_label = QLabel("—F"); app.curr_f_prog_label.setStyleSheet("font-weight: bold;")
    app.end_f_label = QLabel("— F"); app.end_f_label.setStyleSheet(f"color: {T.MUTED};")
    pb_bot.addWidget(app.start_f_label); pb_bot.addStretch(); pb_bot.addWidget(app.curr_f_prog_label); pb_bot.addStretch(); pb_bot.addWidget(app.end_f_label)
    prog_layout.addLayout(pb_bot)
    app.right_layout.addWidget(app.prog_card)
    
    # 렌더 정보 카드
    app._card_labels = {}
    app._info_vars = {}
    app.info_card = GlowCard()
    info_layout = QGridLayout(app.info_card)
    info_layout.setContentsMargins(20, 20, 20, 20)
    info_layout.setVerticalSpacing(8); info_layout.setHorizontalSpacing(4)
    info_layout.setColumnStretch(1, 1)
    
    card_keys = ["software","renderer","doc","render_set","take","resolution",
                 "frame_range","start_time","end_time","total_elapsed","output_path"]
    for i, key in enumerate(card_keys):
        lbl = QLabel("")
        lbl.setStyleSheet(f"color: {T.MUTED}; font-size: 13px;") 
        lbl.setFixedWidth(110); lbl.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        
        val = QLabel("—")
        val.setWordWrap(True); val.setMinimumSize(50, 0)
        val.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        val.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        val.setTextInteractionFlags(Qt.TextSelectableByMouse)
        
        if key == "output_path":
            val.setCursor(QCursor(Qt.PointingHandCursor))
            val.setStyleSheet(f"color: {T.BLUE}; text-decoration: underline;")
        
        app._card_labels[key] = lbl
        app._info_vars[key] = val
        info_layout.addWidget(lbl, i, 0); info_layout.addWidget(val, i, 1)
    app.right_layout.addWidget(app.info_card)
    
    # 진행 상세 카드
    app.prog_detail_card = GlowCard()
    detail_layout = QGridLayout(app.prog_detail_card)
    detail_layout.setContentsMargins(20, 20, 20, 20)
    detail_layout.setVerticalSpacing(20); detail_layout.setHorizontalSpacing(16)
    
    app._prog_labels = {}
    LAYOUT = [
        ("current_frame_time", 0, 0), ("last_frame", 0, 1), ("avg_frame", 0, 2),
        ("elapsed", 1, 0), ("remaining", 1, 1), ("eta", 1, 2)
    ]
    for key, r, c in LAYOUT:
        v_box = QVBoxLayout(); v_box.setSpacing(2)
        lbl = QLabel(""); lbl.setStyleSheet(f"color: {T.MUTED}; font-size: 13px;")
        val = QLabel("—"); val.setStyleSheet("font-size: 15px; font-weight: 500;")
        app._prog_labels[key] = lbl
        app._info_vars[key] = val
        v_box.addWidget(lbl); v_box.addWidget(val)
        detail_layout.addLayout(v_box, r, c)
    app.right_layout.addWidget(app.prog_detail_card)
    
    # 로그 섹션
    log_hdr_layout = QHBoxLayout()
    app._log_section_lbl = QLabel("Log")
    app._log_section_lbl.setStyleSheet(f"color: {T.MUTED}; font-weight: bold;")
    log_hdr_layout.addWidget(app._log_section_lbl); log_hdr_layout.addStretch()
    app.right_layout.addLayout(log_hdr_layout)
    
    app.log_container = GlowCard()
    log_inner_layout = QVBoxLayout(app.log_container)
    log_inner_layout.setContentsMargins(12, 12, 12, 12)
    app.log_text = QTextEdit()
    app.log_text.setMinimumHeight(120); app.log_text.setReadOnly(True)
    app.log_text.setStyleSheet("font-size: 10px; line-height: 120%;")
    log_inner_layout.addWidget(app.log_text)
    app.right_layout.addWidget(app.log_container)
    
    app.right_layout.addStretch()
    app.right_scroll.setWidget(right_content)
    content_layout.addWidget(app.right_scroll, 1)
    main_layout.addWidget(content)
    
    # 리사이즈 그립
    app.size_grip_wrap = QWidget(app)
    app.size_grip_wrap.setFixedSize(32, 32)
    sg_layout = QVBoxLayout(app.size_grip_wrap)
    sg_layout.setContentsMargins(0, 0, 4, 4); sg_layout.setSpacing(0)
    size_grip = CustomSizeGrip(app)
    sg_layout.addWidget(size_grip, 0, Qt.AlignBottom | Qt.AlignRight)

# ── 상태 도우미 ───────────────────────────────────────────────────────────────
def update_status_badge(label, text, fg, bg):
    """상태 뱃지의 텍스트와 색상을 업데이트합니다."""
    label.setText(text)
    label.setStyleSheet(f"background-color: {bg}; color: {fg}; font-weight: bold; padding: 4px 8px; border-radius: 4px;")

def update_progress_bar(bar, pct_label, pct, color):
    """프로그레스 바와 퍼센트 라벨을 업데이트합니다."""
    bar.setValue(int(pct * 1000))
    bar.setStyleSheet(f"""
        QProgressBar::chunk {{ background-color: {color}; border-radius: 4px; }}
        QProgressBar {{ background-color: {T.BORDER}; border-radius: 4px; }}
    """)
    pct_label.setText(f"{pct*100:.1f}%")
    pct_label.setStyleSheet(f"color: {color}; font-weight: bold;")

def update_info_label(label, value):
    """정보 라벨의 텍스트를 안전하게 업데이트합니다."""
    if not label: return
    text = str(value)
    if label.text() != text:
        label.setText(text)

def reset_main_view(app):
    """메인 화면의 모든 정보와 이미지를 초기 상태로 비웁니다."""
    for key in app._info_vars:
        update_info_label(app._info_vars.get(key), "—")
    app.app_title_lbl.setText("—")
    app.status_badge.setText("")
    app.pct_label.setText("0.0%")
    app.progress_bar.setValue(0)
    
    app.first_img_label.setPixmap(QPixmap())
    app.first_img_label.setText("No Image")
    app.last_img_label.setPixmap(QPixmap())
    app.last_img_label.setText("No Image")
    
    pid_text = app.g("pid", "PID")
    app.pid_label.setText(f"{pid_text}: —")

def prepare_session_view(app):
    """새 세션 시작 시 썸네일 라벨을 초기화하고 상단으로 스크롤합니다."""
    app.first_img_label.setText("No Image")
    app.last_img_label.setText("No Image")
    app.first_img_label.setPixmap(QPixmap())
    app.last_img_label.setPixmap(QPixmap())
    scroll_to_top(app)

def update_status_by_key(app, key, fg, bg):
    """번역 키와 색상을 받아 상태 뱃지를 업데이트합니다."""
    txt = app.g(key)
    if app.status_badge.text() == txt and app.status_badge.property("status_key") == key:
        return
    update_status_badge(app.status_badge, txt, fg, bg)
    app.status_badge.setProperty("status_key", key)

def update_progress(app, pct, color):
    """진행 바와 퍼센트 라벨을 통합 업데이트합니다."""
    if not hasattr(app, "progress_bar"): return
    update_progress_bar(app.progress_bar, app.pct_label, pct, color)

def focus_window(app):
    """윈도우 순정 애니메이션을 동반하여 창을 최상단으로 가져옵니다."""
    if app.isActiveWindow() and not app.isMinimized():
        return
    if app.isMinimized():
        app.showNormal()
    else:
        app.showMinimized()
        from PySide6.QtCore import QTimer
        QTimer.singleShot(50, app.showNormal)
        QTimer.singleShot(50, app.activateWindow)
    app.activateWindow()

def scroll_to_top(app):
    """사이드바와 메인 레이아웃의 스크롤을 최상단으로 이동합니다."""
    from PySide6.QtCore import QTimer
    if hasattr(app, "sidebar_scroll"):
        app.sidebar_scroll.verticalScrollBar().setValue(0)
        QTimer.singleShot(100, lambda: app.sidebar_scroll.verticalScrollBar().setValue(0))
    
    if hasattr(app, "right_scroll"):
        app.right_scroll.verticalScrollBar().setValue(0)
        QTimer.singleShot(100, lambda: app.right_scroll.verticalScrollBar().setValue(0))

def play_sound(app, sound_type):
    """지정된 사운드 파일을 재생합니다."""
    import os
    from utils import path_manager
    from PySide6.QtCore import QUrl
    s_path = os.path.join(path_manager.SOUNDS_DIR, f"{sound_type}.mp3")
    if os.path.exists(s_path):
        app.player.setSource(QUrl.fromLocalFile(s_path))
        app.player.play()

def update_volume_icon(app, is_muted):
    """볼륨 상태에 따라 아이콘을 업데이트합니다."""
    if hasattr(app, 'volume_btn'):
        app.volume_btn.setText("🔇" if is_muted else "🔊")

def update_render_info(app, init, upd, fmt_time_func):
    """텍스트 기반 렌더링 정보를 UI에 일괄 업데이트합니다."""
    sw = init.get("software", "—")
    update_info_label(app._info_vars.get("software"), sw)
    update_info_label(app._info_vars.get("renderer"), init.get("renderer", "—"))
    
    doc_name = init.get("doc_name", "")
    update_info_label(app._info_vars.get("doc"), doc_name if doc_name else "—")
    app.app_title_lbl.setText(doc_name if doc_name else "—")
    
    # Blender일 경우 특정 필드 숨김 처리
    is_blender = (sw.upper() == "BLENDER")
    for key in ["render_set", "take"]:
        if key in app._card_labels:
            app._card_labels[key].setVisible(not is_blender)
            app._info_vars[key].setVisible(not is_blender)
            
    if not is_blender:
        update_info_label(app._info_vars.get("render_set"), init.get("render_setting", "—"))
        update_info_label(app._info_vars.get("take"), init.get("take_name", "—"))

    update_info_label(app._info_vars.get("resolution"), f"{init.get('res_x',0)} × {init.get('res_y',0)}")
    update_info_label(app._info_vars.get("frame_range"), f"{init.get('start_frame',0)} – {init.get('end_frame',0)}  ({init.get('total_frames',0)} frames)")
    update_info_label(app._info_vars.get("start_time"), init.get("start_time","—"))
    
    path = init.get("output_path","")
    update_info_label(app._info_vars.get("output_path"), path.replace("\\", "\\\u200b").replace("/", "/\u200b") if path else "—")
    
    update_info_label(app._info_vars.get("current_frame_time"), upd.get("field_current_frame_time", "—"))
    update_info_label(app._info_vars.get("last_frame"), fmt_time_func(upd.get("last_frame_duration", 0)))
    update_info_label(app._info_vars.get("avg_frame"), fmt_time_func(upd.get("avg_frame_duration", 0)))
    update_info_label(app._info_vars.get("elapsed"), fmt_time_func(upd.get("elapsed_seconds", 0)))
    
    app.start_f_label.setText(f"{init.get('start_frame','—')} F")
    app.end_f_label.setText(f"{init.get('end_frame','—')} F")
    app.curr_f_prog_label.setText(f"{upd.get('current_frame',0)}F")

def update_thumbnail_label(app, label, thumb_path):
    """썸네일 라벨에 이미지를 그리고 마스크를 적용합니다."""
    pix = QPixmap(thumb_path)
    if not pix.isNull():
        masked_pix = mask_rounded_pixmap(pix, radius=12)
        label.setPixmap(masked_pix)
        label.setText("")
        return True
    else:
        label.setPixmap(QPixmap())
        label.setText("No Image")
        return False

def add_history_card(app, path, data, status_color, load_callback, menu_callback, top=True):
    """새로운 히스토리 카드를 생성하여 사이드바에 추가합니다."""
    try:
        basename = os.path.basename(path)
        date_part = basename[len("Render_"):-len(".json")]
        dt = time.strptime(date_part, "%Y%m%d_%H%M%S")
        label = time.strftime("%Y-%m-%d %H:%M:%S", dt)
    except: 
        label = os.path.basename(path)
    
    card = HistoryCard(path, label, data["doc_name"], data["software"], status_color)
    card.clicked.connect(load_callback)
    card.rightClicked.connect(menu_callback)
    
    if top:
        app.sidebar_layout_inner.insertWidget(0, card)
    else:
        app.sidebar_layout_inner.insertWidget(app.sidebar_layout_inner.count() - 1, card)
        
    app._history_btns[path] = card
    return card

def sync_history_sidebar(app, history_files, get_data_func, get_color_func, load_callback, menu_callback):
    """파일 목록에 맞춰 사이드바 위젯들을 최신화합니다."""
    current_paths = set(history_files)
    known_paths = set(app._history_btns.keys())
    
    # 1. 삭제된 파일 위젯 제거
    removed_paths = known_paths - current_paths
    for p in removed_paths:
        btn = app._history_btns.pop(p, None)
        if btn: btn.deleteLater()
        app._history_mtimes.pop(p, None)

    # 2. 추가된 파일 위젯 생성
    added_paths = current_paths - known_paths
    if added_paths:
        # 정렬된 리스트(history_files)에서 새로 추가된 것만 역순으로 순회하며 상단에 삽입
        for path in reversed(history_files):
            if path in added_paths:
                data = get_data_func(path)
                color = get_color_func(path)
                app._history_mtimes[path] = os.path.getmtime(path)
                add_history_card(app, path, data, color, load_callback, menu_callback, top=True)
    
    # 3. 기존 파일 내용 변경 체크 (색상 등)
    for path in history_files:
        if path in known_paths:
            try:
                mt = os.path.getmtime(path)
                if mt != app._history_mtimes.get(path, 0):
                    app._history_mtimes[path] = mt
                    color = get_color_func(path)
                    if path in app._history_btns:
                        app._history_btns[path].set_status_color(color)
            except: pass
            
    # 4. 하이라이트 적용
    active_path = app._viewing_file or app._active_file
    for path, card in app._history_btns.items():
        card.set_active(path == active_path)

def apply_ui_translations(app):
    """애플리케이션의 모든 UI 텍스트에 번역을 적용합니다."""
    # 최상단 타이틀바 고정
    app.title_bar.title_label.setText("MW Render Monitor")
    
    app.prog_hdr_lbl.setText(app.g("progress_label", "Progress"))
    app.sb_hdr_lbl.setText(app.g("history", "Render History"))
    
    # 볼륨 아이콘 업데이트
    if app.is_muted:
        app.volume_btn.setText("🔇")
    else:
        app.volume_btn.setText("🔊")
    
    pid_text = app.g("pid", "PID")
    cur_pid = (app.watched_pid if app.watched_pid else "—")
    app.pid_label.setText(f"{pid_text}: {cur_pid}")
    
    # 정보 카드 번역 매핑
    INFO_MAP = {
        "software": "ui_software", "renderer": "ui_renderer", "doc": "ui_doc", "render_set": "ui_render_set",
        "take": "ui_take", "resolution": "ui_resolution", "frame_range": "ui_frame_range",
        "start_time": "ui_start_time", "end_time": "ui_end_time", 
        "total_elapsed": "ui_elapsed", "output_path": "ui_output_path"
    }
    for key, lbl in app._card_labels.items():
        app_msg_key = INFO_MAP.get(key, f"ui_{key}")
        lbl.setText(app.app_msgs.get(app_msg_key, key))
        
    # 진행도 정보 번역 매핑
    PROG_MAP = {
        "current_frame_time": "field_current_frame_time", "last_frame": "ui_last_frame",
        "avg_frame": "ui_avg_frame", "elapsed": "ui_elapsed",
        "remaining": "ui_remaining", "eta": "ui_eta"
    }
    for key, lbl in app._prog_labels.items():
        app_msg_key = PROG_MAP.get(key, f"ui_{key}")
        lbl.setText(app.app_msgs.get(app_msg_key, key))
        
    app._log_section_lbl.setText(app.g("log", "Log"))
    
    # 현재 상태 뱃지 텍스트 갱신
    if app.last_status:
        key_map = {
            "Progress": "progress", "Started": "started", "Finished": "finished", 
            "Stopped": "stopped", "Crashed": "crashed", "NotResponding": "not_responding",
            "SoftwareClosed": "software_closed"
        }
        badge_key = key_map.get(app.last_status, app.last_status.lower())
        app.status_badge.setText(app.g(badge_key, app.last_status))

def trigger_main_glow(app, color_hex):
    """창 전체 글로우 효과를 트리거합니다."""
    if not hasattr(app, "glow_overlay"): return
    
    # 트리거 시 크기 재조정 및 최상단으로 올리기
    app.glow_overlay.resize(app.width(), app.height() - 34)
    app.glow_overlay.raise_()
    
    if hasattr(app, "_glow_anim") and app._glow_anim: 
        app._glow_anim.stop()
        
    app._glow_anim = trigger_glow_anim(app.glow_overlay, "intensity", color_hex)
