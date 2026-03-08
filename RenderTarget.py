import sys
import os
import json
import time
import threading
import socket
import traceback
import psutil
from utils import constants
from utils import path_manager
from utils import config_manager
from core import engine
from ui import interface
from core import messenger
from ui.styles import T, STYLE_SHEET_TEMPLATE

# 데이터 및 폴더 초기화
path_manager.ensure_directories()

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QScrollArea, QFrame, QGridLayout,
    QProgressBar, QTextEdit, QMenu, QSystemTrayIcon
)
from PySide6.QtGui import QFontDatabase, QFont, QPixmap, QIcon, QCursor, QColor, QAction
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput

# 예외 처리기 설정
sys.excepthook = engine.handle_exception

# --- Main Application Controller ---
class RenderTrackerMonitor(QMainWindow):
    socket_signal = Signal(dict) # 소켓 메시지 처리를 위한 시그널

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
        self.state_engine = engine.RenderStateEngine(self.start_app_ts)
        self._init_state_vars()
        
        # 오디오 및 시스템 트레이 설정
        self._setup_audio()
        self._setup_tray_icon()
        
        # UI 구성 및 초기 데이터 로드 (시작 시 불필요한 알림 방지)
        self._build_ui()
        interface.apply_ui_translations(self)
        self._load_initial_data()
        
        # 모니터링 타이머 및 소켓 서버 시작
        self.main_timer = QTimer(self)
        self.main_timer.timeout.connect(self._update_app_state)
        self.main_timer.start(constants.POLLING_INTERVAL_MS)

        self.socket_signal.connect(self._on_socket_received)
        self._start_socket_server()

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
        self.last_init = {} # [Fix] For crash notifications
        self.last_upd = {}  # [Fix] For crash notifications
        self._first_img_path = None
        self._first_img_mtime = 0
        self._last_img_path = None
        self._last_img_mtime = 0

    def _load_initial_data(self):
        """앱 시작 시 가장 최근의 렌더 기록을 모니터링 대상으로 설정 (Silent 로드)"""
        latest = engine.get_latest_render_file()
        if latest:
            try:
                with open(latest, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self._active_file = latest
                    
                    # [Fix] 초기 가동 시 상태 엔진 동기화 및 경로 정합성 확보
                    # 현재 진행 중인 상태라면 실시간 모드로 로드하여 감지 가능하게 함
                    status = engine.determine_render_status(init, data.get("update", {}), end)
                    is_progress = (status == "Progress")
                    
                    self._viewing_file = None if is_progress else latest
                    events = self.state_engine.detect_events(data, from_history=not is_progress)
                    self._process(data, latest, events, from_history=not is_progress) 
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
        engine.log_to_file(msg, level)
        self.log_text.append(line)
        scrollbar = self.log_text.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def _highlight_sidebar(self, path=None):
        """사이드바의 특정 항목을 강조 표시 (현재는 전체 갱신으로 대체)"""
        self._refresh_sidebar()

    def _open_settings(self):
        dlg = interface.SettingsDialog(self, self.cfg, self.app_msgs, self._on_cfg_changed)
        dlg.exec()

    def _open_output_folder(self):
        """현재 렌더링 결과물이 저장되는 폴더를 엽니다."""
        # last_init에서 경로를 가져오거나, state_engine에 저장된 데이터에서 가져옵니다.
        path = self.last_init.get("output_path") if hasattr(self, 'last_init') else None
        if path and os.path.exists(path):
            os.startfile(path)
        else:
            self._log("Output path not found or invalid", "WARNING")

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

    # --- Network Socket Server ---
    def _start_socket_server(self):
        """백그라운드에서 소켓 서버를 시작합니다."""
        port = self.cfg.get("socket_port", constants.DEFAULT_PORT)
        threading.Thread(target=self._socket_server_loop, args=(port,), daemon=True).start()
        self._log(f"Socket server standby (Port: {port})")

    def _socket_server_loop(self, port):
        """실제 TCP 수신 루프"""
        try:
            server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            # 포트 재사용 설정 (앱 재시작 시 포트 바인딩 에러 방지)
            server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server.bind(('127.0.0.1', port))
            server.listen(5)
            
            while True:
                conn, addr = server.accept()
                try:
                    data = conn.recv(8192) # 긴 경로 대비 8KB 수신
                    if data:
                        msg = json.loads(data.decode('utf-8'))
                        self.socket_signal.emit(msg)
                except Exception as e:
                    engine.log_to_file(f"Socket receive error: {e}", "ERROR")
                finally:
                    conn.close()
        except Exception as e:
            self._log(f"Socket server critical error: {e}", "ERROR")
            engine.log_to_file(f"Socket Server Crash:\n{traceback.format_exc()}", "CRITICAL")

    def _save_socket_data_to_file(self, msg):
        """소켓으로 전달받은 렌더링 상태를 JSON 히스토리 파일로 저장합니다."""
        event_type = msg.get("event", "UNKNOWN")
        
        # 새 세션(START)이거나 켤 때부터 렌더링 중이었다면 새 파일 생성
        if event_type == "START" or not self._active_file:
            ts_str = time.strftime("%Y%m%d_%H%M%S")
            self._active_file = os.path.join(path_manager.HISTORY_DIR, f"Render_{ts_str}.json")
            
        if self._active_file:
            try:
                with open(self._active_file, "w", encoding="utf-8") as f:
                    json.dump(msg, f, ensure_ascii=False, indent=2)
            except Exception as e:
                engine.log_to_file(f"Failed to save socket data: {e}", "ERROR")
            return self._active_file
        return None

    def _on_socket_received(self, msg):
        """소켓에서 수신된 데이터를 파싱하고 저장 및 UI에 반영합니다."""
        event_type = msg.get("event", "UNKNOWN")
        
        # 소켓 수신 데이터를 예쁘게 줄바꿈하여 UI 로그와 파일 로그에 모두 기록
        formatted_msg = json.dumps(msg, indent=2, ensure_ascii=False)
        self._log(f"Socket Data Received [{event_type}]:\n{formatted_msg}", "DEBUG")
        
        # 1. 파일로 저장하여 히스토리 유지
        saved_path = self._save_socket_data_to_file(msg)
        if not saved_path: return
        
        # [신규 추가] 세션 동기화 로직
        # 새로운 세션이 시작되거나, 배경에서 렌더링이 종료(FINISH/STOP)된 경우 자동 전환 처리
        if event_type in ("START", "FINISH", "STOP"):
            # 과거기록 시청 중 배경에서 렌더 이벤트가 발생하면 실시간 뷰로 자동 점프
            if self._viewing_file:
                self._log(f"Auto-switching: Background render {event_type}")
                self._viewing_file = None

            # 세션 정보 동기화 (START이거나 활성 파일이 바뀐 경우)
            if event_type == "START" or self._active_file != saved_path:
                self._active_file = saved_path
                self.watched_pid = msg.get("start", {}).get("dcc_pid")
                
                if event_type == "START":
                    self.crash_sent = False
                    soft = msg.get("start", {}).get("software", "Unknown")
                    self._log(f"Session Changed: [{soft}] (PID:{self.watched_pid})")

            # 시작/종료 이벤트 발생 시 사이드바(상태 아이콘 등) 갱신
            self._refresh_sidebar()

        # 2. 실시간 시간 보정 (파이썬에서 경과시간/ETA 직접 계산)
        msg = engine.enrich_realtime_metrics(msg)
        
        # 3. 모델 폴링(detect_events) 및 UI 업데이트
        # 과거 기록 시청 중이 아닐 때만 즉각 반영
        if not self._viewing_file:
            events = self.state_engine.detect_events(msg, from_history=False)
            self._process(msg, saved_path, events, from_history=False)

    # --- Polling & Data Handling ---
    def _refresh_sidebar(self):
        """히스토리 파일 목록을 스캔하여 사이드바 위젯 동기화"""
        # print("refresh sidebar")
        history_files = engine.get_history_files()
        interface.sync_history_sidebar(
            self, history_files, 
            engine.get_history_item_data, 
            lambda p: engine.get_status_color_from_file(p, {'YELLOW': T.YELLOW, 'GREEN': T.GREEN, 'RED': T.RED}),
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
            
            # [Fix] 히스토리 로드 시에도 시간/지표 보정 적용
            data = engine.enrich_realtime_metrics(data)

            # [Fix] 히스토리 로드 시 즉각적인 상태 반영 (상태 엔진 동기화 및 UI 강제 갱신)
            events = self.state_engine.detect_events(data, from_history=True)
            self.last_status = None 
            self._process(data, path, events, from_history=True)
        except Exception as e:
            self._log(f"[History] {e}")

    def _update_app_state(self):
        """단일 책임 원칙: 0.5초마다 (1) 크래시 감시 (2) 활성 렌더 UI 시계 갱신"""
        try:
            # 1. 프로세스 크래시 감시 (진행 중인 렌더링에만 해당)
            if self.watched_pid and not self.crash_sent:
                try:
                    p = psutil.Process(self.watched_pid)
                    if not p.is_running() or p.status() == psutil.STATUS_ZOMBIE:
                        self._log(f"Process termination detected (PID: {self.watched_pid})")
                        self.crash_sent = True
                        self._on_crash()
                except psutil.NoSuchProcess:
                    self._log(f"Process termination detected (PID: {self.watched_pid})")
                    self.crash_sent = True
                    self._on_crash()
                except Exception:
                    pass

            # 2. 실시간 시계 갱신 (과거 기록을 보고 있지 않고, 진행 중인 상태일 때)
            if not self._viewing_file and self.state_engine.last_status == "Progress" and self.state_engine.last_known_data:
                # 파일 I/O 없이 메모리 상의 마지막 데이터를 가져옴
                data_to_process = engine.enrich_realtime_metrics(self.state_engine.last_known_data)
                events = self.state_engine.detect_events(data_to_process, from_history=False)
                # 데이터와 그 데이터의 출처(Path)를 함께 묶어서 전달
                if self._active_file:
                    self._process(data_to_process, self._active_file, events, from_history=False)

        except Exception as e:
            err_details = traceback.format_exc()
            self._log(f"Polling error: {str(e)}", "ERROR")
            engine.log_to_file(f"Detailed Polling Error:\n{err_details}", "ERROR")

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
        if engine.delete_history_files(path):
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
            if engine.clear_all_render_history():
                self._log("Cleared all history")
                self._viewing_file = self._active_file = None
                interface.reset_main_view(self)
                self._refresh_sidebar()
            else:
                self._log("Error clearing history", "ERROR")

    def _process(self, data, target_path, events=None, from_history=False):
        """UI 액션 센터: 넘겨받은 데이터를 기반으로 UI, Glow, 사운드 실행"""
        try:
            if events is None: events = []
            init, upd, end = data.get("start", {}), data.get("update", {}), data.get("end", {})
            
            # [Fix] 크래시 상황 대비 최신 데이터 보관
            self.last_init = init
            self.last_upd = upd
            
            ren, tot = upd.get("rendered_frames", 0), init.get("total_frames", 1)
            is_realtime = not from_history
            software = init.get("software", "Unknown")
            
            # 실시간 데이터 로깅 (필요 시)
            if is_realtime and "FRESH_START" in events:
                self._log(f"Processing real-time data for {software}")

            # 0. 세션 시작 처리 (캐시 초기화 등)
            if "SESSION_STARTED" in events:
                self.progress_msg_id = None
                self._reset_thumbnail_cache()
                self._refresh_sidebar() # 새 파일 감지 시 사이드바 갱신
                if is_realtime:
                    interface.prepare_session_view(self)

            # 1. 최우선 피드백 처리 (Glow, 사운드 등 반응형 최우선)
            status = self.state_engine.last_status
            if "FRESH_START" in events:
                self._handle_render_started_feedback(init)
            
            if "FRESH_END" in events:
                self._handle_render_ended_feedback(status, init, upd, end)

            # 2. UI 텍스트 및 상태 뱃지 업데이트 (상세 정보 채우기)
            interface.update_render_info(self, init, upd, engine.fmt_time)

            # 3. 진행도/완료 상태별 UI 세부 분기
            pct = ren / tot if tot > 0 else 0.0
            if status == "Progress":
                self._handle_progress_update(upd, pct, events, init, is_realtime)
            elif status in ("Finished", "Stopped"):
                self._handle_render_ended_ui(status, events, init, upd, end, is_realtime, pct)

            # 4. 실시간 썸네일 프로세싱 (의존성 주입: target_path 전달)
            self._update_thumbnails(init, upd, target_path, from_history)
        except Exception as e:
            err_details = traceback.format_exc()
            self._log(f"Process error: {str(e)}", "ERROR")
            engine.log_to_file(f"Detailed Process Error:\n{err_details}", "ERROR")


    def _handle_render_started_feedback(self, init):
        """시작 시 즉각 피드백 (Glow/Sound) 및 외부 알림"""
        interface.trigger_main_glow(self, T.BLUE)
        interface.play_sound(self, "Start")
        interface.focus_window(self)
        QApplication.alert(self, 0)
        self._log(f"New render detected (TS: {init.get('start_ts')})")
        threading.Thread(target=self._messenger_started, args=(dict(init),), daemon=True).start()

    def _handle_render_ended_feedback(self, status, init, upd, end):
        """종료 시 즉각 피드백 (Glow/Sound) 및 외부 알림"""
        is_fin = (status == "Finished")
        interface.trigger_main_glow(self, T.GREEN if is_fin else T.RED)
        interface.play_sound(self, "End" if is_fin else "Error")
        interface.focus_window(self)
        self._refresh_sidebar() # 종료 상태 반영을 위해 사이드바 갱신
        threading.Thread(target=self._messenger_finished, args=(dict(init), dict(upd), dict(end), is_fin, self._last_img_path), daemon=True).start()

    def _handle_progress_update(self, upd, pct, events, init, is_realtime):
        """진행 중 상태의 UI 갱신 및 디스코드 알림"""
        # [Fix] 실시간 시간 데이터 (남은 시간, ETA, 경과 시간)는 매 프레임 상시 업데이트
        rem = upd.get("remaining_seconds", -1)
        interface.update_info_label(self._info_vars.get("remaining"), engine.fmt_time(rem) if rem >= 0 else "—")
        interface.update_info_label(self._info_vars.get("eta"), time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(time.time()+rem)) if (is_realtime and rem >= 0) else "—")
        interface.update_info_label(self._info_vars.get("end_time"), "—")
        interface.update_info_label(self._info_vars.get("total_elapsed"), engine.fmt_time(upd.get("elapsed_seconds", 0)))

        # 상태 뱃지 및 최초 진입 처리
        if self.last_status != "Progress" or not is_realtime:
            self.last_status = "Progress"
            interface.update_status_by_key(self, "progress", T.YELLOW, T.BADGE_YELLOW)
        
        interface.update_progress(self, pct, T.YELLOW)
        if "PROGRESS_UPDATED" in events and is_realtime:
            threading.Thread(target=self._messenger_progress, args=(dict(init), dict(upd), self.progress_msg_id, self._last_img_path), daemon=True).start()

    def _reset_thumbnail_cache(self):
        """세션 시작 시 썸네일 캐시 초기화"""
        self._last_thumb_update_ts = 0
        self._last_thumb_frame_num = -1
        self._first_img_path = self._last_img_path = None
        self._first_img_mtime = self._last_img_mtime = 0

    def _handle_render_ended_ui(self, status, events, init, upd, end, is_realtime, pct):
        """종료 시 UI 세부 요소 업데이트"""
        # [구조적 개선] 히스토리 모드이거나 상태 전이 이벤트가 있을 때 UI 갱신 허용
        if not is_realtime or f"STATUS_TO_{status.upper()}" in events:
            self.last_status = status
            is_fin = (status == "Finished")
            interface.update_info_label(self._info_vars.get("current_frame_time"), self._info_vars["last_frame"].text())
            interface.update_info_label(self._info_vars.get("remaining"), "—")
            interface.update_info_label(self._info_vars.get("eta"), "—")
            interface.update_info_label(self._info_vars.get("end_time"), end.get("end_time","—"))
            interface.update_info_label(self._info_vars.get("total_elapsed"), engine.fmt_time(upd.get("elapsed_seconds", 0)))
            interface.update_status_by_key(self, status.lower(), (T.GREEN if is_fin else T.RED), (T.BADGE_GREEN if is_fin else T.BADGE_RED))
            interface.update_progress(self, pct, (T.GREEN if is_fin else T.RED))
            if is_realtime: interface.scroll_to_top(self)

    def _update_thumbnails(self, init, upd, target_path, from_history):
        """실시간 썸네일 업데이트 로직"""

        # 8. 썸네일 업데이트 (앱에서 직접 복사 및 리사이징 처리)
        # 중요: 렌더 중 실시간 경로는 init 대신 upd에서 가져와야 최신화됩니다.
        curr_path = upd.get("last_frame_path")
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

        # JSON 파일명을 기반으로 저장될 썸네일 이름 결정 (의존성 주입된 target_path 사용)
        json_basename = os.path.basename(target_path)
        curr_f = upd.get("current_frame", 0)
        
        for cfg in base_configs:
            raw_source = init.get(cfg["key"])
            if not raw_source:
                # [Fix] 소스 경로가 없을 경우에만 No Image 표시
                cfg["label"].setPixmap(QPixmap())
                cfg["label"].setText("No Image")
                continue


            # 원본 파일 해소 (로직 분리)
            actual_source = engine.resolve_image_path(raw_source)
            
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
                if engine.process_thumbnail(actual_source, thumb_path):
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
        """렌더링 프로세스 비정상 종료 시 처리: 오직 데이터 갱신만 수행"""
        try:
            soft = self.last_init.get("software", "DCC")
            pid_str = f" (PID: {self.watched_pid})" if self.watched_pid else ""
            self._log(f"{soft} process ended{pid_str}")
            
            # JSON 강제 업데이트 (분리된 로직 호출)
            # 사운드/글로우/알림 등 피드백은 데이터 변화를 감지한 상태 엔진이 다음 루프에서 처리하도록 위임
            if engine.force_update_json_on_crash(self._active_file):
                self._log(f"Force updated JSON on process end: {os.path.basename(self._active_file)}")

        except Exception as e:
            self._log(f"Crash handler error: {str(e)}", "ERROR")

    def _messenger_started(self, init):
        """렌더링 시작 시 디스코드 알림 전송"""
        mid = messenger.notify_started(init, self.cfg, self.msgs)
        if mid: self._log("Started Discord notified")

    def _messenger_progress(self, init, upd, captured, thumb_path=None):
        """렌더링 진행 중 디스코드 알림 업데이트"""
        new_id = messenger.notify_progress(init, upd, self.cfg, self.msgs, captured, thumb_path=thumb_path)
        if new_id and new_id != captured:
            self.progress_msg_id = new_id

    def _messenger_finished(self, init, upd, end, is_fin, thumb_path=None):
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
    engine.setup_dpi_awareness()
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
    
    window = RenderTrackerMonitor()
    window.show()
    window.raise_()
    window.activateWindow()
    
    sys.exit(app.exec())