"""
MW Render Monitor  —  PySide6 (shadcn-inspired dark UI)
"""

import sys
import os
import json
import time
import threading
import traceback
import constants
import path_manager
import config_manager
import render_processor
import interface
import messenger
from styles import T, STYLE_SHEET_TEMPLATE
from datetime import datetime

path_manager.ensure_directories()


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

# (Paths now managed via path_manager.py)

sys.excepthook = render_processor.handle_exception

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
        self.cfg = config_manager.load_config()
        
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
        self.app_msgs = config_manager.load_messages(self._app_lang)
        self.msgs = config_manager.load_messages(self.cfg.get("language", "ko"))
        
        self.start_app_ts = time.time()
        self.last_start_ts = None
        self.last_status = None
        self.last_rendered_frames = -1
        self.progress_msg_id = None
        self.watched_pid = None
        self.crash_sent = False
        self.last_init = {}
        self.last_upd = {}
        
        # 상태 전이 엔진 초기화
        self.state_engine = render_processor.RenderStateEngine(self.start_app_ts)
        
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
        self._log(f"Watching: {path_manager.HISTORY_DIR}")
        
        self.poll_timer = QTimer(self)
        self.poll_timer.timeout.connect(self._poll)
        self.poll_timer.start(constants.POLLING_INTERVAL_MS)

        # Glow Overlay (창 전체 은은하게 빛나기)
        self.glow_overlay = interface.MainGlowOverlay(self)
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
        # 인터페이스 빌더를 호출하여 레이아웃 구성 (interface.py로 위임)
        interface.build_main_ui(self)
        
        # 버튼 시그널 연결
        self.volume_btn.clicked.connect(self._toggle_mute)
        self.settings_btn.clicked.connect(self._open_settings)
        
        # 출력 경로 클릭 이벤트 연결
        if "output_path" in self._info_vars:
            self._info_vars["output_path"].mousePressEvent = lambda e: self._open_output_folder()
        
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
        config_manager.save_config(self.cfg)
        
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
        icon_path = os.path.join(path_manager.IMAGES_DIR, "Icon_Setting.png")
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
        # 깜빡임 방지용 체크 로직은 상위 호출부에서 유지
        if self.status_badge.text() == txt and self.status_badge.property("status_key") == key:
            return
        interface.update_status_badge(self.status_badge, txt, fg, bg)
        self.status_badge.setProperty("status_key", key)


    def _set_bar(self, pct, color):
        if not hasattr(self, "progress_bar"): return
        interface.update_progress_bar(self.progress_bar, self.pct_label, pct, color)

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
        render_processor.log_to_file(msg, level)
        self.log_text.append(line)
        scrollbar = self.log_text.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def _trigger_glow(self, color_hex):
        """창 전체 글로우 효과를 트리거합니다."""
        if not hasattr(self, "glow_overlay"): return
        # 트리거 시 크기 재조정
        self.glow_overlay.resize(self.width(), self.height() - 34)
        self.glow_overlay.raise_()
        
        if self._glow_anim: self._glow_anim.stop()
        self._glow_anim = interface.trigger_glow_anim(self.glow_overlay, "intensity", color_hex)

    def _open_settings(self):
        dlg = interface.SettingsDialog(self, self.cfg, self.app_msgs, self._on_cfg_changed)
        dlg.exec()

    def _on_cfg_changed(self, new_cfg):
        prev_lang = self._app_lang
        self.cfg = new_cfg
        self.msgs = config_manager.load_messages(new_cfg.get("language","ko"))
        self._app_lang = new_cfg.get("app_language","ko")
        self.app_msgs = config_manager.load_messages(self._app_lang)
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
                dlg = interface.CustomMessageBox(self, self.g("app_title"), msg)
                dlg.exec()

    # ── 히스토리 및 폴링 로직 ────────────────────────────────────────────────────────
    def _get_latest_render_file(self):
        return render_processor.get_latest_render_file()

    def _refresh_sidebar(self):
        history_files = render_processor.get_history_files()
        interface.sync_history_sidebar(
            self, history_files, 
            render_processor.get_history_item_data, 
            self._get_status_color_from_file,
            self._load_history, 
            self._show_history_context_menu
        )

    def _get_status_color_from_file(self, path):
        color_map = {'YELLOW': T.YELLOW, 'GREEN': T.GREEN, 'RED': T.RED}
        return render_processor.get_status_color_from_file(path, color_map)

    def _load_history(self, path):
        self._viewing_file = path
        # 하이라이트 즉시 갱신 (지휘자 판단)
        self._refresh_sidebar()
        
        # [Fix] 항목 변경 시 이미지 캐시 초기화
        self._first_img_path = self._last_img_path = None
        self._first_img_mtime = self._last_img_mtime = 0
        
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
        if render_processor.delete_history_files(path):
            self._log(f"Removed history: {os.path.basename(path)}")
            # 현재 보고 있는 파일 삭제 시 뷰 초기화
            if self._viewing_file == path or self._active_file == path:
                self._viewing_file = None
                if self._active_file == path: self._active_file = None
                self._reset_main_view()
            self._refresh_sidebar()
        else:
            self._log(f"Error removing history: {os.path.basename(path)}", "ERROR")

    def _clear_all_history(self):
        msg = "Are you sure you want to delete ALL render history?"
        if self._app_lang == "ko":
            msg = "정말 모든 렌더 기록을 삭제하시겠습니까?"
            
        dlg = interface.CustomMessageBox(self, self.g("ui_history"), msg)
        if dlg.exec():
            if render_processor.clear_all_render_history():
                self._log("Cleared all history")
                self._viewing_file = self._active_file = None
                self._reset_main_view()
                self._refresh_sidebar()
            else:
                self._log("Error clearing history", "ERROR")

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
        return interface.mask_rounded_pixmap(pixmap, radius)

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
        
        # 2. 이벤트 감지 (상태 전이 엔진 위임)
        events = self.state_engine.detect_events(data, from_history)
        is_realtime = not from_history

        # 3. PID 감시 (프로세스 추적)
        if pid and pid != self.watched_pid:
            self.watched_pid = pid
            self.crash_sent  = False
            interface.update_info_label(self.pid_label, f"{self.g('pid', 'PID')}: {pid}")
            self._log(f"PID: {pid}")
            threading.Thread(target=self._watch_pid, args=(pid,), daemon=True).start()

        # 4. 이벤트별 처리 (지휘)
        if "SESSION_STARTED" in events:
            self.progress_msg_id = None
            self.crash_sent = False
            self._last_thumb_update_ts = 0
            self._last_thumb_frame_num = -1
            self._first_img_path = self._last_img_path = None
            self._first_img_mtime = self._last_img_mtime = 0
            
            if is_realtime:
                self.first_img_label.setPixmap(QPixmap()); self.first_img_label.setText("No Image")
                self.last_img_label.setPixmap(QPixmap());  self.last_img_label.setText("No Image")
                self._scroll_to_top(sidebar=True)

        if "FRESH_START" in events:
            self._log(f"New render detected (TS: {start_ts})")
            threading.Thread(target=self._do_started, args=(dict(init),), daemon=True).start()
            self._play_render_sound("Start")
            self._activate_main_window()
            QApplication.alert(self, 0)
            self._trigger_glow(T.BLUE)

        # 상태 결정 및 UI 업데이트
        status = self.state_engine.last_status
        interface.update_render_info(self, init, upd, render_processor.fmt_time)

        # 5. 상태별 상세 로직
        pct = ren / tot if tot > 0 else 0.0
        
        if status == "Progress":
            # [Fix] 외부에서 이미 '응답 없음'으로 판단된 경우, 단순히 '진행 중'으로 덮어쓰지 않음
            if self.last_status == "NotResponding" and is_realtime:
                pass 
            else:
                self.last_status = "Progress"
                rem = upd.get("remaining_seconds", -1)
                interface.update_info_label(self._info_vars.get("remaining"), render_processor.fmt_time(rem) if rem >= 0 else "—")
                interface.update_info_label(self._info_vars.get("eta"), time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(time.time()+rem)) if rem >= 0 else "—")
                interface.update_info_label(self._info_vars.get("end_time"), "—")
                interface.update_info_label(self._info_vars.get("total_elapsed"), render_processor.fmt_time(upd.get("elapsed_seconds", 0)))
                self._set_status("progress", T.YELLOW, T.BADGE_YELLOW)
            self._set_bar(pct, T.YELLOW)

            if "PROGRESS_UPDATED" in events and is_realtime:
                threading.Thread(target=self._do_progress, args=(dict(init), dict(upd), self.progress_msg_id, self._last_img_path), daemon=True).start()

        elif status in ("Finished", "Stopped"):
            if f"STATUS_TO_{status.upper()}" in events:
                if is_realtime: self._log(f"→ {status}")
                self.last_status = status
                
                interface.update_info_label(self._info_vars.get("current_frame_time"), self._info_vars["last_frame"].text())
                interface.update_info_label(self._info_vars.get("remaining"), "—")
                interface.update_info_label(self._info_vars.get("eta"), "—")
                interface.update_info_label(self._info_vars.get("end_time"), end.get("end_time","—"))
                interface.update_info_label(self._info_vars.get("total_elapsed"), render_processor.fmt_time(upd.get("elapsed_seconds", 0)))
                
                is_fin = (status == "Finished")
                self._set_status(status.lower(), (T.GREEN if is_fin else T.RED), (T.BADGE_GREEN if is_fin else T.BADGE_RED))
                self._set_bar(pct, (T.GREEN if is_fin else T.RED))
                if is_realtime: self._scroll_to_top(sidebar=True)

            if "FRESH_END" in events:
                is_fin = (status == "Finished")
                self._trigger_glow(T.GREEN if is_fin else T.RED)
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


            # 원본 파일 해소 (로직 분리)
            actual_source = render_processor.resolve_image_path(raw_source)
            
            if not actual_source:
                cfg["label"].setPixmap(QPixmap())
                cfg["label"].setText("No Image")
                continue

            thumb_path = os.path.join(path_manager.HISTORY_DIR, json_basename.replace(".json", cfg["suffix"]))
            
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
                if render_processor.process_thumbnail(actual_source, thumb_path):
                    # 화면 표시용 Pixmap 변환 (로직 분리 - interface.py)
                    interface.update_thumbnail_label(self, cfg["label"], thumb_path)
                    
                    # 상태 기록
                    setattr(self, cfg["path_attr"], thumb_path)
                    setattr(self, processed_key, actual_source)
                    if cfg["throttle"]:
                        self._last_thumb_update_ts = now_ts
                        self._last_thumb_frame_num = curr_f
                        self._log(f"Thumbnail updated: Frame {curr_f}")
                else:
                    cfg["label"].setPixmap(QPixmap())
                    cfg["label"].setText("No Image")

            else:
                # 이미 처리된 파일이 있는 경우 화면 로딩 (로직 분리 - interface.py)
                current_shown = getattr(self, cfg["path_attr"], None)
                if not current_shown or current_shown != thumb_path:
                    if interface.update_thumbnail_label(self, cfg["label"], thumb_path):
                        setattr(self, cfg["path_attr"], thumb_path)

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
        
        # JSON 강제 업데이트 (분리된 로직 호출)
        if render_processor.force_update_json_on_crash(self._active_file):
            self._log(f"Force updated JSON on process end: {os.path.basename(self._active_file)}")

        self._set_status("crashed", T.RED, T.BADGE_RED)
        self._trigger_glow(T.RED)
        self._set_bar(self.progress_bar.value() / 1000.0, T.RED)
        self._play_render_sound("Error")
        self._activate_main_window()
        self._scroll_to_top()
        threading.Thread(target=messenger.notify_crash, args=(self.last_init, self.last_upd, self.cfg, self.msgs), daemon=True).start()

    def _do_started(self, init):
        mid = messenger.notify_started(init, self.cfg, self.msgs)
        if mid: self._log("Started Discord notified")

    def _do_progress(self, init, upd, captured, thumb_path=None):
        new_id = messenger.notify_progress(init, upd, self.cfg, self.msgs, captured, thumb_path=thumb_path)
        if new_id and new_id != captured:
            self.progress_msg_id = new_id

    def _do_finished(self, init, upd, end, is_fin, thumb_path=None):
        messenger.notify_finished(init, upd, end, self.cfg, self.msgs, is_fin, pmid=self.progress_msg_id, thumb_path=thumb_path)

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
        config_manager.save_config(self.cfg)
        self._update_volume()
        self._log(f"Volume: {'Muted' if self.is_muted else f'{new_vol}%'}")

    def _play_render_sound(self, sound_type):
        sound_dir = path_manager.SOUNDS_DIR
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
    render_processor.setup_dpi_awareness()
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    
    app = QApplication(sys.argv)
    
    # OS 호환 QFontDatabase로 Pretendard 폰트 로딩
    fonts_loaded = False
    for fname in ["Pretendard-Regular.otf", "Pretendard-Medium.otf", "Pretendard-SemiBold.otf", "Pretendard-Bold.otf",
                  "Pretendard-Regular.ttf", "Pretendard-Medium.ttf", "Pretendard-SemiBold.ttf", "Pretendard-Bold.ttf"]:
        path = os.path.join(path_manager.FONTS_DIR, fname)
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