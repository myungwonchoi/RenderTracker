class T:
    BG      = "#09090b"   # zinc-950
    CARD    = "#18181b"   # zinc-900
    BORDER  = "#27272a"   # zinc-800
    INPUT   = "#09090b"
    FG      = "#fafafa"   # zinc-50
    MUTED   = "#a1a1aa"   # zinc-400 (Contrast improved)
    MUTED2  = "#a1a1aa"   # zinc-400

    GREEN   = "#22c55e"
    YELLOW  = "#eab308"
    BLUE    = "#3b82f6"
    RED     = "#ef4444"
    ORANGE  = "#f97316"

    BADGE_GREEN  = "#052e16"
    BADGE_YELLOW = "#1c1500"
    BADGE_BLUE   = "#0c1a3a"
    BADGE_RED    = "#1c0505"

    # ── 애니메이션 설정 (밀리초 단위)
    GLOW_PEAK_MS = 300   # 최대 강도에 도달하는 시간
    GLOW_EXIT_MS = 2500  # 피크 이후 사라지는 시간
    GLOW_INTENSITY = 0.3 # 글로우의 최대 강도 (0.0 ~ 1.0)
    GLOW_SPREAD = 100    # 글로우가 퍼지는 범위 (픽셀)

STYLE_SHEET_TEMPLATE = f"""
QWidget {{
    font-family: {{FONT_FAMILY}};
    color: {T.FG};
}}
QMainWindow, #MainBackground {{
    background-color: {T.BG};
    border: 1px solid {T.BORDER};
    border-radius: 12px;
}}
QScrollArea, QScrollArea > QWidget > QWidget {{
    background-color: {T.BG};
    border: none;
}}
#Card {{
    background-color: {T.CARD};
    border: 1px solid {T.BORDER};
    border-radius: 12px;
}}
#TitleBar {{
    background-color: {T.BORDER};
    border-top-left-radius: 12px;
    border-top-right-radius: 12px;
}}
#TitleBar QLabel {{
    font-size: 11px;
    font-weight: 500;
    color: {T.MUTED};
}}

#TitleBar QPushButton {{
    background-color: transparent;
    border: none;
    color: {T.MUTED};
    font-size: 14px;
}}
#TitleBar QPushButton:hover {{
    color: {T.FG};
    background-color: {T.MUTED};
}}
#TitleBar #CloseBtn:hover {{
    background-color: #e11d48;
    color: white;
}}
QScrollBar:vertical {{
    border: none;
    background: transparent;
    width: 5px;
    margin: 4px 1px;
}}
QScrollBar::handle:vertical {{
    background: {T.BORDER};
    min-height: 40px;
    border-radius: 2px;
}}
QScrollBar::handle:vertical:hover {{
    background: {T.MUTED};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical, QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
    background: none;
    height: 0px;
}}
QScrollBar:horizontal {{
    border: none;
    background: transparent;
    height: 5px;
    margin: 1px 4px;
}}
QScrollBar::handle:horizontal {{
    background: {T.BORDER};
    min-width: 40px;
    border-radius: 2px;
}}
QScrollBar::handle:horizontal:hover {{
    background: {T.MUTED};
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal, QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
    background: none;
    width: 0px;
}}
QProgressBar {{
    background-color: {T.BORDER};
    border: none;
    border-radius: 4px;
    text-align: right;
    color: transparent; /* 텍스트 숨김 */
}}
QProgressBar::chunk {{
    background-color: {T.GREEN}; /* 기본색 (동적으로 변경됨) */
    border-radius: 4px;
}}
#SettingsBtn {{
    background-color: {T.CARD};
    border: 1px solid {T.BORDER};
    border-radius: 4px;
    qproperty-text: ""; 
    min-width: 32px;
    max-width: 32px;
    min-height: 32px;
    max-height: 32px;
}}
#VolumeBtn {{
    background-color: {T.CARD};
    border: 1px solid {T.BORDER};
    border-radius: 4px;
    qproperty-text: "";
    min-width: 32px;
    max-width: 32px;
    min-height: 32px;
    max-height: 32px;
}}
#SettingsBtn:hover, #VolumeBtn:hover {{
    background-color: {T.BORDER};
}}
QSlider::track:horizontal {{
    height: 4px;
    background: {T.BORDER};
    border-radius: 2px;
}}
QSlider::handle:horizontal {{
    background: {T.BLUE};
    width: 14px;
    height: 14px;
    margin: -5px 0;
    border-radius: 7px;
}}
QLineEdit {{
    background-color: {T.INPUT};
    border: 1px solid {T.BORDER};
    padding: 6px;
    border-radius: 4px;
    color: {T.FG};
    font-size: 13px;
}}

QLineEdit:focus {{
    border: 1px solid {T.BLUE};
}}
QTextEdit {{
    background-color: transparent;
    color: {T.MUTED2};
    border: none;
}}
QPushButton#PrimaryBtn {{
    background-color: {T.BLUE};
    color: {T.FG};
    font-weight: bold;
    border: none;
    border-radius: 4px;
    padding: 8px 16px;
}}
QPushButton#PrimaryBtn:hover {{
    background-color: #2563eb;
}}
QPushButton#SecondaryBtn {{
    background-color: {T.CARD};
    color: {T.FG};
    border: 1px solid {T.BORDER};
    border-radius: 4px;
    padding: 8px 16px;
}}
QPushButton#SecondaryBtn:hover {{
    background-color: {T.BORDER};
}}
QRadioButton, QCheckBox {{
    background-color: transparent;
    color: {T.FG};
    spacing: 8px;
    outline: none;
    font-size: 13px;
}}
QRadioButton::indicator, QCheckBox::indicator {{
    width: 18px;
    height: 18px;
    border: 2px solid {T.BORDER};
    background-color: {T.INPUT};
}}
QCheckBox::indicator {{
    border-radius: 4px;
}}
QRadioButton::indicator {{
    border-radius: 9px; /* 완전한 원형 */
}}
QCheckBox::indicator:checked {{
    background-color: {T.BLUE};
    border: 2px solid {T.BLUE};
    image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'%3E%3Cpath fill='white' d='M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z'/%3E%3C/svg%3E");
}}
QRadioButton::indicator:checked {{
    border: 2px solid {T.BLUE};
    image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'%3E%3Ccircle fill='%233b82f6' cx='12' cy='12' r='7'/%3E%3C/svg%3E");
}}
QRadioButton::indicator:hover, QCheckBox::indicator:hover {{
    border: 2px solid {T.MUTED};
}}
QRadioButton::indicator:disabled, QCheckBox::indicator:disabled {{
    background-color: {T.BORDER};
}}
QMenu {{
    background-color: {T.CARD};
    border: 1px solid {T.BORDER};
    border-radius: 6px;
    padding: 4px;
}}
QMenu::item {{
    padding: 6px 20px;
    border-radius: 4px;
    color: {T.FG};
}}
QMenu::item:selected {{
    background-color: {T.BORDER};
}}
QMenu::separator {{
    height: 1px;
    background: {T.BORDER};
    margin: 4px 0px;
}}
"""
