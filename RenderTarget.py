import sys
import os
import json
import time
import threading
import traceback
import psutil
from utils import constants
from utils import path_manager
from utils import config_manager
from core import engine as core
from ui import interface
from core import messenger
from ui.styles import T, STYLE_SHEET_TEMPLATE
from datetime import datetime

# 데이터 및 폴더 초기화
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

# 예외 처리기 설정
sys.excepthook = core.handle_exception

# --- Main Application Controller ---
class RenderMonitorApp(QMainWindow):
    def __init__(self):
        super().__init__()
        # 기본 윈도우 속성 설정 (Frameless, 반투명 등)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Window | Qt.WindowMinMaxButtonsHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_StaticContents, True)
        self.resize(920, 950)
        self.setMinimumSize(600, 600)
        self.setMaximumHeight(1080)
        
        # UI 및 설정 초기화
        self._setup_native_window()
        self.cfg = config_manager.load_config()
        self._restore_window_geometry()
        
        self._app_lang = self.cfg.get("app_language", "ko")
        self.app_msgs = config_manager.load_messages(self._app_lang)
        self.msgs = config_manager.load_messages(self.cfg.get("language", "ko"))
        
        # 상태 관리 엔진 및 초기 데이터 변수
        self.start_app_ts = time.time()
        self.state_engine = core.RenderStateEngine(self.start_app_ts)
        self.monitor = core.RenderMonitor(self.state_engine)
        self._init_state_vars()
        
        # 오디오 및 시스템 트레이 설정
        self._setup_audio()
        self._setup_tray_icon()
        
        # UI 구성 및 초기 데이터 로드 (시작 시 불필요한 알림 방지)
        self._build_ui()
        interface.apply_ui_translations(self)
        self._load_initial_data()
        
        # 모니터링 타이머 시작
        self.poll_timer = QTimer(self)
        self.poll_timer.timeout.connect(self._poll)
        self.poll_timer.start(constants.POLLING_INTERVAL_MS)

        # 시각 효과 오버레이
        self.glow_overlay = interface.MainGlowOverlay(self)
        self.glow_overlay.setGeometry(0, 34, self.width(), self.height() - 34)
        self.glow_overlay.lower() 
        self._glow_anim = None

    def _init_state_vars(self):
        """내부 상태 관리용 변수 초기화"""
        self.last_start_ts = None
        self.last_status = None
        self.last_rendered_frames = -1
        self.progress_msg_id = None
        self.watched_pid = None
        self.crash_sent = False
        self._active_file = None
        self._viewing_file = None
        self._history_btns = {}
        self._history_mtimes = {}
        self.last_init = {}
        self.last_upd = {}
        self._first_img_path = None
        self._first_img_mtime = 0
        self._last_img_path = None
        self._last_img_mtime = 0

    def _load_initial_data(self):
        """앱 시작 시 가장 최근의 렌더 기록을 모니터링 대상으로 설정 (Silent 로드)"""
        latest = core.get_latest_render_file()
        if latest:
            try:
                with open(latest, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.last_start_ts = data.get("start", {}).get("start_ts")
                    self._active_file = latest
                    # 초기 데이터 로드 (Silent)
                    self._process(data, from_history=True) 
            except: pass

    def _restore_window_geometry(self):
        """저장된 창 위치 및 크기 복원"""
        geom = self.cfg.get("window_geometry")
        if geom:
            try: self.restoreGeometry(bytes.fromhex(geom))
            except: self._center_window()
        else:
            self._center_window()

    def _setup_audio(self):
        """오디오 출력 장치 및 초기 볼륨 설정"""
        self.audio_output = QAudioOutput()
        self.player = QMediaPlayer()
        self.player.setAudioOutput(self.audio_output)
        self.is_muted = (self.cfg.get("volume", 50) == 0)
        self.last_non_zero_volume = self.cfg.get("volume", 50) if not self.is_muted else 50
        self._update_volume()
        
    def _setup_native_window(self):
        """Windows 11 네이티브 라운드 코너 효과 강제 적용"""
        if sys.platform == "win32":
            import ctypes
            from ctypes import wintypes
            hwnd = self.winId()
            # DWM API 호출
            dwmapi = ctypes.windll.dwmapi
            dwmapi.DwmSetWindowAttribute(
                wintypes.HWND(hwnd), 33,
                ctypes.byref(ctypes.c_int(2)),
                ctypes.sizeof(ctypes.c_int)
            )

    def _center_window(self):
        """화면 중앙에 창 배치"""
        qr = self.frameGeometry()
        cp = self.screen().availableGeometry().center()
        qr.moveCenter(cp)
        self.move(qr.topLeft())

    # --- UI Events & Transitions ---
    def _build_ui(self):
        """메인 레이아웃 구성 및 이벤트 연결"""
        interface.build_main_ui(self)
        self.volume_btn.clicked.connect(self._toggle_mute)
        self.settings_btn.clicked.connect(self._open_settings)
        if "output_path" in self._info_vars:
            self._info_vars["output_path"].mousePressEvent = lambda e: self._open_output_folder()

    def resizeEvent(self, event):
        """창 크기 조절 시 자식 위젯 및 레이어 동기화"""
        super().resizeEvent(event)
        if hasattr(self, 'size_grip_wrap'):
            self.size_grip_wrap.move(self.width() - 32, self.height() - 32)
        if hasattr(self, 'glow_overlay') and not self.glow_overlay.isHidden():
            self.glow_overlay.move(0, 34)
            self.glow_overlay.resize(self.width(), self.height() - 34)

    def closeEvent(self, event):
        """창 닫기 시 상태 저장 및 트레이로 숨김 처리"""
        self.cfg["window_geometry"] = self.saveGeometry().toHex().data().decode()
        config_manager.save_config(self.cfg)
        
        if self.tray_icon.isVisible():
            self.hide()
            event.ignore()
            self._log("Minimized to system tray")
        else:
            event.accept()

    def _setup_tray_icon(self):
        """트레이 메뉴 및 아이콘 구성"""
        self.tray_icon = QSystemTrayIcon(self)
        icon_path = os.path.join(path_manager.IMAGES_DIR, "Icon_Setting.png")
        if os.path.exists(icon_path):
            self.tray_icon.setIcon(QIcon(icon_path))
        
        tray_menu = QMenu()
        tray_menu.addAction(self.g("ui_show", "Show"), lambda: interface.focus_window(self))
        tray_menu.addSeparator()
        tray_menu.addAction(self.g("ui_exit", "Exit"), self._actual_quit)
        
        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.activated.connect(self._on_tray_activated)
        self.tray_icon.show()

    def _on_tray_activated(self, reason):
        """트레이 아이콘 클릭/더블클릭 시 창 띄움"""
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            if self.isVisible():
                self.hide()
            else:
                interface.focus_window(self)

    def _actual_quit(self):
        """앱을 완전히 종료"""
        self.tray_icon.hide()
        QApplication.quit()

    def g(self, key, default=""):
        """번역 메시지 검색 헬퍼"""
        return self.app_msgs.get(f"ui_{key}", self.app_msgs.get(key, default or key))

    def _log(self, msg, level="INFO"):
        """콘솔 및 UI 화면에 로그 출력"""
        ts = time.strftime("%H:%M:%S")
        line = f"[{ts}] {msg}"
        print(line)
        core.log_to_file(msg, level)
        self.log_text.append(line)
        scrollbar = self.log_text.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def _highlight_sidebar(self, path=None):
        """사이드바의 특정 항목을 강조 표시 (현재는 전체 갱신으로 대체)"""
        self._refresh_sidebar()

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
            interface.apply_ui_translations(self)
        self._update_volume()
        self._log("Settings updated")

    # --- Polling & Data Handling ---
    def _refresh_sidebar(self):
        """히스토리 파일 목록을 스캔하여 사이드바 위젯 동기화"""
        history_files = core.get_history_files()
        interface.sync_history_sidebar(
            self, history_files, 
            core.get_history_item_data, 
            lambda p: core.get_status_color_from_file(p, {'YELLOW': T.YELLOW, 'GREEN': T.GREEN, 'RED': T.RED}),
            self._load_history, 
            self._show_history_context_menu
        )

    def _load_history(self, path):
        """특정 히스토리 파일 데이터를 읽어 메인 뷰에 로드"""
        self._viewing_file = path
        self._refresh_sidebar()
        
        # 이미지 캐시 초기화
        self._first_img_path = self._last_img_path = None
        self._first_img_mtime = self._last_img_mtime = 0
        
        if not os.path.exists(path):
            self._log(f"[History] File not found: {os.path.basename(path)}")
            return
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            self._process(data, from_history=True)
        except Exception as e:
            self._log(f"[History] {e}")

    def _poll(self):
        """메인 모니터링 루프: 엔진에 의뢰하여 상태 감시 및 UI 갱신"""
        try:
            # 1. 사이드바 및 상태 갱신은 항시 수행 (사용자 요청)
            self._refresh_sidebar()

            # 2. 엔진에 폴링 의뢰 (비즈니스 로직 분리)
            res = self.monitor.poll(self._active_file, self._viewing_file, self.watched_pid)

            # 3. 결과에 따른 처리
            if res["crashed"] and not self.crash_sent:
                self.crash_sent = True
                QTimer.singleShot(0, self._on_crash)

            if res["new_active"]:
                self._active_file = res["new_active"]
                self._viewing_file = None
                self._log(f"New render detected: {os.path.basename(res['new_active'])}")
                # 새로운 렌더링 감지 즉시 UI 컨텍스트 전환 (사이드바 하이라이트 및 메인 뷰 초기화)
                self._refresh_sidebar()
                interface.reset_main_view(self)

            if res.get("active_ended") and self._viewing_file:
                self._log("Background render ended. Switching to active view.")
                self._viewing_file = None
                # 즉시 뷰 전환을 위해 사이드바 및 UI 초기화
                self._refresh_sidebar()
                interface.reset_main_view(self)
                interface.scroll_to_top(self)

            if res["hang_detected"] and self.last_status != "NotResponding":
                self._log("Potential render hang detected", "WARNING")
                self.last_status = "NotResponding"
                interface.update_status_by_key(self, "not_responding", T.ORANGE, T.BADGE_RED)

            if res["data"]:
                self._process(res["data"], from_history=res["is_history"])

        except Exception as e:
            self._log(f"Polling error: {str(e)}", "ERROR")

    def _show_history_context_menu(self, path):
        """히스토리 항목에 대한 컨텍스트 메뉴 표시"""
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
        """특정 히스토리 항목 삭제"""
        if core.delete_history_files(path):
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
        """모든 렌더 히스토리 삭제"""
        msg = "Are you sure you want to delete ALL render history?"
        if self._app_lang == "ko":
            msg = "정말 모든 렌더 기록을 삭제하시겠습니까?"
            
        dlg = interface.CustomMessageBox(self, self.g("ui_history"), msg)
        if dlg.exec():
            if core.clear_all_render_history():
                self._log("Cleared all history")
                self._viewing_file = self._active_file = None
                interface.reset_main_view(self)
                self._refresh_sidebar()
            else:
                self._log("Error clearing history", "ERROR")

    def _process(self, data, from_history=False):
        """렌더링 데이터(JSON)를 해석하고 상태 전이에 따른 비즈니스 로직 및 UI 업데이트 수행"""
        init, upd, end = data.get("start", {}), data.get("update", {}), data.get("end", {})
        ren, tot = upd.get("rendered_frames", 0), init.get("total_frames", 1)
        
        # 1. 상태 전이 엔진을 통한 이벤트 감지
        events = self.state_engine.detect_events(data, from_history)
        is_realtime = not from_history

        # 2. PID 관리 및 쓰레드 감시 시작
        if init.get("c4d_pid") and init["c4d_pid"] != self.watched_pid:
            self.watched_pid = init["c4d_pid"]
            self.crash_sent = False
            interface.update_info_label(self.pid_label, f"{self.g('pid', 'PID')}: {self.watched_pid}")
            threading.Thread(target=self._watch_pid, args=(self.watched_pid,), daemon=True).start()

        # 3. 주요 상태 이벤트 대응 (지휘)
        if "SESSION_STARTED" in events:
            self.progress_msg_id = None
            self._reset_thumbnail_cache()
            if is_realtime:
                interface.prepare_session_view(self)

        if "FRESH_START" in events:
            self._handle_render_started(init)

        # 4. 정보 패널 및 상태 뱃지 갱신
        status = self.state_engine.last_status
        interface.update_render_info(self, init, upd, core.fmt_time)

        # 5. 진행도/완료 상태별 UI 분기
        pct = ren / tot if tot > 0 else 0.0
        if status == "Progress":
            self._handle_progress_update(upd, pct, events, init, is_realtime)
        elif status in ("Finished", "Stopped"):
            self._handle_render_ended(status, events, init, upd, end, is_realtime, pct)

        # 6. 실시간 썸네일 프로세싱
        self._update_thumbnails(init, upd, from_history)

    def _handle_render_started(self, init):
        """새로운 렌더링 시작 시 필요한 작업 수행"""
        self._log(f"New render detected (TS: {init.get('start_ts')})")
        threading.Thread(target=self._do_started, args=(dict(init),), daemon=True).start()
        interface.play_sound(self, "Start")
        interface.focus_window(self)
        QApplication.alert(self, 0)
        interface.trigger_main_glow(self, T.BLUE)

    def _reset_thumbnail_cache(self):
        """세션 시작 시 썸네일 캐시 초기화"""
        self._last_thumb_update_ts = 0
        self._last_thumb_frame_num = -1
        self._first_img_path = self._last_img_path = None
        self._first_img_mtime = self._last_img_mtime = 0

    def _handle_progress_update(self, upd, pct, events, init, is_realtime):
        """진행 중 상태의 UI 갱신 및 디스코드 알림"""
        if self.last_status != "NotResponding" or not is_realtime:
            self.last_status = "Progress"
            rem = upd.get("remaining_seconds", -1)
            interface.update_info_label(self._info_vars.get("remaining"), core.fmt_time(rem) if rem >= 0 else "—")
            interface.update_info_label(self._info_vars.get("eta"), time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(time.time()+rem)) if rem >= 0 else "—")
            interface.update_info_label(self._info_vars.get("end_time"), "—")
            interface.update_info_label(self._info_vars.get("total_elapsed"), core.fmt_time(upd.get("elapsed_seconds", 0)))
            interface.update_status_by_key(self, "progress", T.YELLOW, T.BADGE_YELLOW)
        
        interface.update_progress(self, pct, T.YELLOW)
        if "PROGRESS_UPDATED" in events and is_realtime:
            threading.Thread(target=self._do_progress, args=(dict(init), dict(upd), self.progress_msg_id, self._last_img_path), daemon=True).start()

    def _handle_render_ended(self, status, events, init, upd, end, is_realtime, pct):
        """렌더링 종료(성공/정지) 처리"""
        if f"STATUS_TO_{status.upper()}" in events:
            self.last_status = status
            is_fin = (status == "Finished")
            
            interface.update_info_label(self._info_vars.get("current_frame_time"), self._info_vars["last_frame"].text())
            interface.update_info_label(self._info_vars.get("remaining"), "—")
            interface.update_info_label(self._info_vars.get("eta"), "—")
            interface.update_info_label(self._info_vars.get("end_time"), end.get("end_time","—"))
            interface.update_info_label(self._info_vars.get("total_elapsed"), core.fmt_time(upd.get("elapsed_seconds", 0)))
            
            interface.update_status_by_key(self, status.lower(), (T.GREEN if is_fin else T.RED), (T.BADGE_GREEN if is_fin else T.BADGE_RED))
            interface.update_progress(self, pct, (T.GREEN if is_fin else T.RED))
            if is_realtime: interface.scroll_to_top(self)

        if "FRESH_END" in events:
            is_fin = (status == "Finished")
            interface.trigger_main_glow(self, T.GREEN if is_fin else T.RED)
            threading.Thread(target=self._do_finished, args=(dict(init), dict(upd), dict(end), is_fin, self._last_img_path), daemon=True).start()
            interface.play_sound(self, "End" if is_fin else "Error")
            interface.focus_window(self)

    def _update_thumbnails(self, init, upd, from_history):
        """실시간 썸네일 업데이트 로직"""

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
        curr_f = upd.get("current_frame", 0)
        
        for cfg in base_configs:
            raw_source = init.get(cfg["key"])
            if not raw_source:
                # [Fix] 소스 경로가 없을 경우에만 No Image 표시
                cfg["label"].setPixmap(QPixmap())
                cfg["label"].setText("No Image")
                continue


            # 원본 파일 해소 (로직 분리)
            actual_source = core.resolve_image_path(raw_source)
            
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
                if core.process_thumbnail(actual_source, thumb_path):
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
        """지정된 PID의 프로세스 종료를 감시"""
        try: psutil.Process(pid).wait()
        except: pass
        finally:
            if self.last_status not in ("Finished","Stopped") and not self.crash_sent:
                self.crash_sent = True
                QTimer.singleShot(0, self._on_crash) # 메인 스레드에서 실행

    def _on_crash(self):
        """렌더링 프로세스 비정상 종료 시 처리"""
        self._log("C4D process ended (Crash or Closed)")
        self.last_status = "Crashed"
        
        # JSON 강제 업데이트 (분리된 로직 호출)
        if core.force_update_json_on_crash(self._active_file):
            self._log(f"Force updated JSON on process end: {os.path.basename(self._active_file)}")

        interface.update_status_by_key(self, "crashed", T.RED, T.BADGE_RED)
        interface.trigger_main_glow(self, T.RED)
        interface.update_progress(self, self.progress_bar.value() / 1000.0, T.RED)
        interface.play_sound(self, "Error")
        interface.focus_window(self)
        interface.scroll_to_top(self)
        threading.Thread(target=messenger.notify_crash, args=(self.last_init, self.last_upd, self.cfg, self.msgs), daemon=True).start()

    def _do_started(self, init):
        """렌더링 시작 시 디스코드 알림 전송"""
        mid = messenger.notify_started(init, self.cfg, self.msgs)
        if mid: self._log("Started Discord notified")

    def _do_progress(self, init, upd, captured, thumb_path=None):
        """렌더링 진행 중 디스코드 알림 업데이트"""
        new_id = messenger.notify_progress(init, upd, self.cfg, self.msgs, captured, thumb_path=thumb_path)
        if new_id and new_id != captured:
            self.progress_msg_id = new_id

    def _do_finished(self, init, upd, end, is_fin, thumb_path=None):
        """렌더링 완료/정지 시 디스코드 알림 전송"""
        messenger.notify_finished(init, upd, end, self.cfg, self.msgs, is_fin, pmid=self.progress_msg_id, thumb_path=thumb_path)

    def _update_volume(self):
        """볼륨 설정 및 UI 업데이트"""
        vol = self.cfg.get("volume", 50)
        self.is_muted = (vol == 0)
        if not self.is_muted:
            self.last_non_zero_volume = vol
        self.audio_output.setVolume(vol / 100.0)
        
        # 버튼 아이콘 즉시 반영
        if hasattr(self, 'volume_btn'):
            self.volume_btn.setText("🔇" if self.is_muted else "🔊")
        interface.update_volume_icon(self, self.is_muted)

    def _toggle_mute(self):
        """음소거 상태 토글"""
        if self.is_muted:
            new_vol = self.last_non_zero_volume
        else:
            self.last_non_zero_volume = self.cfg.get("volume", 50)
            new_vol = 0
            
        self.cfg["volume"] = new_vol
        config_manager.save_config(self.cfg)
        self._update_volume()
        self._log(f"Volume: {'Muted' if self.is_muted else f'{new_vol}%'}")

# --- Entry Point ---
if __name__ == "__main__":
    core.setup_dpi_awareness()
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    
    app = QApplication(sys.argv)
    
    # 폰트 로딩 (Pretendard 우선순위)
    fonts_loaded = False
    for fname in ["Pretendard-Regular.otf", "Pretendard-Medium.otf", "Pretendard-SemiBold.otf", "Pretendard-Bold.otf",
                  "Pretendard-Regular.ttf", "Pretendard-Medium.ttf", "Pretendard-SemiBold.ttf", "Pretendard-Bold.ttf"]:
        path = os.path.join(path_manager.FONTS_DIR, fname)
        if os.path.exists(path) and QFontDatabase.addApplicationFont(path) != -1:
            fonts_loaded = True
    
    # 폰트 및 스타일 글로벌 적용
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