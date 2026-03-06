bl_info = {
    "name": "RenderTracker (Blender)",
    "description": "Writes render status JSON files for RenderTracker.",
    "author": "Antigravity",
    "version": (1, 0, 0),
    "blender": (3, 0, 0),
    "location": "Properties > Render Properties",
    "category": "Render",
}

import bpy
import json
import os
import time
import shutil
import atexit
from bpy.props import StringProperty
from bpy.types import AddonPreferences

# 전역 상태 변수
class RenderState:
    render_start_ts = 0.0
    start_time_str = ""
    render_start_time = 0.0
    last_frame_time = 0.0
    frame_start_time = 0.0
    total_frame_duration = 0.0
    completed_frames_count = 0
    current_frame = 0
    total_frames = 1
    doc_name = "Untitled"
    take_name = "Main"
    render_setting_name = "Blender Render"
    res_x = 0
    res_y = 0
    start_frame = 0
    end_frame = 0
    output_path = ""
    status_file_name = ""
    current_frame_time_str = ""
    last_frame_duration = 0.0
    last_frame_image_path = ""
    first_frame_image_path = ""
    first_frame_saved = False
    last_thumb_time = 0.0
    render_active = False # 렌더링 활성 상태 플래그 (중복 방지 및 강제 종료 감지용)

state = RenderState()


def format_duration(seconds):
    if seconds < 0: seconds = 0
    s = int(seconds)
    m = s // 60
    h = m // 60
    s %= 60
    m %= 60
    return f"{h:02d}:{m:02d}:{s:02d}"

def write_status_json(elapsed_seconds, remaining_seconds, avg_frame_duration, last_frame_duration, current_frame_duration, end_ts):
    history_path = os.path.join(os.environ.get('APPDATA', ''), 'RenderTracker', 'history')
    
    # history 폴더가 없으면 생성
    if not os.path.exists(history_path):
        try:
            os.makedirs(history_path, exist_ok=True)
        except Exception as e:
            print(f"Render Notification Add-on: Failed to create history directory. {e}")
            return

    file_path = os.path.join(history_path, state.status_file_name)
    end_time_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(end_ts)) if end_ts > 0 else ""

    data = {
        "start": {
            "start_ts": state.render_start_ts,
            "start_time": state.start_time_str,
            "c4d_pid": os.getpid(),
            "doc_name": state.doc_name,
            "take_name": "—",
            "render_setting": "—",
            "res_x": state.res_x,
            "res_y": state.res_y,
            "start_frame": state.start_frame,
            "end_frame": state.end_frame,
            "total_frames": state.total_frames,
            "output_path": state.output_path,
            "software": "Blender",
            "renderer": state.render_setting_name,
            "last_frame_path": state.last_frame_image_path,
            "first_frame_path": state.first_frame_image_path
        },
        "update": {
            "rendered_frames": state.completed_frames_count,
            "current_frame": state.current_frame,
            "elapsed_seconds": elapsed_seconds,
            "remaining_seconds": remaining_seconds,
            "avg_frame_duration": avg_frame_duration,
            "last_frame_duration": last_frame_duration,
            "current_frame_duration": current_frame_duration,
            "field_current_frame_time": state.current_frame_time_str
        },
        "end": {
            "end_ts": end_ts,
            "end_time": end_time_str
        }
    }

    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Render Notification Add-on: Failed to write JSON. {e}")



@bpy.app.handlers.persistent
def on_render_write(scene):
    """프레임 저장이 완료된 시점에 호출됩니다."""
    if not state.status_file_name: return
    
    # 1. 현재 렌더링 완료된 프레임 경로 계산
    raw_path = bpy.path.abspath(scene.render.frame_path(frame=scene.frame_current))
    
    # 2. 확장자 보정
    ext = scene.render.file_extension
    if ext and not raw_path.lower().endswith(ext.lower()):
        raw_path += ext
            
    # 첫 프레임 경로 고정
    if not state.first_frame_saved:
        state.first_frame_image_path = raw_path
        state.first_frame_saved = True
        
    # 마지막 완료 프레임 경로 업데이트
    state.last_frame_image_path = raw_path
    state.current_frame = scene.frame_current
    
    write_status_json_from_state()

def write_status_json_from_state():
    """현재 state 정보를 바탕으로 JSON 갱신 (on_render_post/write 공통 활용)"""
    now = time.time()
    elapsed = now - state.render_start_time
    curr_frame_el = now - state.frame_start_time
    avg = (state.total_frame_duration + curr_frame_el) / (state.completed_frames_count + 1)
    rem = (state.total_frames * avg) - elapsed
    
    # 기존 JSON 저장 함수 호출
    write_status_json(elapsed, rem, avg, 0.0, 0.0, -1.0)


# ── Handlers ──────────────────────────────────────────────────────────────────

@bpy.app.handlers.persistent
def on_render_init(scene):
    state.render_start_time = time.time()
    state.render_start_ts = state.render_start_time
    state.start_time_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(state.render_start_ts))
    state.last_frame_time = state.render_start_time
    state.total_frame_duration = 0.0
    state.completed_frames_count = 0
    state.frame_start_time = state.render_start_time
    state.current_frame = 0
    state.current_frame_time_str = ""
    state.last_frame_image_path = ""
    state.last_thumb_time = 0.0
    state.last_thumb_frame = -1
    state.first_frame_image_path = ""
    state.first_frame_saved = False
    state.render_active = True # 렌더링 시작 표시

    # Generate filename (매 렌더링마다 유니크한 기록 생성)
    state.status_file_name = time.strftime("Render_%Y%m%d_%H%M%S.json", time.localtime(state.render_start_ts))

    # Get scene info
    state.doc_name = bpy.data.filepath.split("\\")[-1].split("/")[-1] if bpy.data.filepath else "Untitled"
    state.take_name = scene.camera.name if scene.camera else "Main"
    engine = scene.render.engine
    engine = scene.render.engine
    if engine in ('BLENDER_EEVEE', 'EEVEE', 'BLENDER_EEVEE_NEXT'):
        state.render_setting_name = "EEVEE"
    elif engine == 'CYCLES':
        state.render_setting_name = "Cycles"
    elif engine == 'BLENDER_WORKBENCH':
        state.render_setting_name = "Workbench"
    else:
        state.render_setting_name = engine.replace('_', ' ').title()
    
    state.res_x = int(scene.render.resolution_x * (scene.render.resolution_percentage / 100.0))
    state.res_y = int(scene.render.resolution_y * (scene.render.resolution_percentage / 100.0))
    
    state.start_frame = scene.frame_start
    state.end_frame = scene.frame_end
    
    # 단일 프레임 렌더인지, 애니메이션 렌더인지 확실히 구분할 수 없으나, 기본적으로 범위를 사용
    state.total_frames = (state.end_frame - state.start_frame) + 1 if state.end_frame >= state.start_frame else 1

    state.output_path = os.path.dirname(bpy.path.abspath(scene.render.frame_path(frame=scene.frame_start)))

    write_status_json(0.0, -1.0, 0.0, 0.0, 0.0, -1.0)
    
    # 1초 주기 실시간 타이머 가동
    bpy.app.timers.register(realtime_update_timer, first_interval=1.0)


@bpy.app.handlers.persistent
def on_render_pre(scene):
    now = time.time()
    last_interval = 0.0
    
    if state.current_frame > 0:
        last_interval = now - state.last_frame_time
        
    state.last_frame_time = now
    state.frame_start_time = now
    state.current_frame += 1
    state.frame_number = scene.frame_current
    state.current_frame_time_str = "00:00:00"
    
    elapsed_seconds = now - state.render_start_time
    # 새로 시작하는 프레임이므로 curr_frame_el은 사실상 0이지만 일관성을 위해 계산
    curr_frame_el = now - state.frame_start_time
    avg_duration = (state.total_frame_duration + curr_frame_el) / (state.completed_frames_count + 1)
    remaining_seconds = (state.total_frames * avg_duration) - elapsed_seconds

    write_status_json(elapsed_seconds, remaining_seconds, avg_duration, last_interval, 0.0, -1.0)


@bpy.app.handlers.persistent
def on_render_post(scene):
    now = time.time()
    current_frame_active_duration = now - state.frame_start_time
    state.last_frame_duration = current_frame_active_duration
    
    state.total_frame_duration += current_frame_active_duration
    state.completed_frames_count += 1
    
    avg_duration = 0.0
    if state.completed_frames_count > 0:
        avg_duration = state.total_frame_duration / state.completed_frames_count

    elapsed_seconds = now - state.render_start_time
    remaining_seconds = (state.total_frames - state.completed_frames_count) * avg_duration if state.total_frames > 0 else -1.0
    
    state.current_frame_time_str = format_duration(current_frame_active_duration)
    
    write_status_json(elapsed_seconds, remaining_seconds, avg_duration, 0.0, current_frame_active_duration, -1.0)


@bpy.app.handlers.persistent
def on_render_complete(scene):
    handle_render_end()

@bpy.app.handlers.persistent
def on_render_cancel(scene):
    handle_render_end()

def handle_render_end():
    # 이미 종료 처리되었으면 중복 수행하지 않음 (C++의 _isFinished와 동일 로직)
    if not state.render_active:
        return
        
    state.render_active = False
    now = time.time()
    elapsed_seconds = now - state.render_start_time
    
    avg_duration = 0.0
    if state.completed_frames_count > 0:
        avg_duration = state.total_frame_duration / state.completed_frames_count

    end_ts = now
    write_status_json(elapsed_seconds, -1.0, avg_duration, state.last_frame_duration, state.last_frame_duration, end_ts)

def realtime_update_timer():
    """엔진 신호와 상관없이 1초마다 강제로 상태를 저장합니다."""
    if not state.render_active:
        return None
    on_render_stats_update(None)
    return 1.0

@bpy.app.handlers.persistent
def on_render_stats_update(scene):
    """렌더링 도중 상태가 변할 때마다 호출됩니다. (타이머 또는 엔진 신호)"""
    if not state.render_active or not state.status_file_name:
        return
        
    now = time.time()
    # 1.0초 주기로 JSON 업데이트 (성능 부하 방지)
    if now - state.last_thumb_time < 1.0:
        return
    state.last_thumb_time = now

    elapsed = now - state.render_start_time
    
    # 현재 프레임 진행 시간 계산
    curr_frame_el = now - state.frame_start_time
    state.current_frame_time_str = format_duration(curr_frame_el)

    # 평균 계산 시 현재 프레임 포함
    avg = (state.total_frame_duration + curr_frame_el) / (state.completed_frames_count + 1)
    
    # 실시간 남은 시간 = (전체 예상 시간) - (이미 경과된 시간)
    rem = (state.total_frames * avg) - elapsed
    if rem < 0: rem = 0.0

    write_status_json(elapsed, rem, avg, state.last_frame_duration, curr_frame_el, -1.0)

@bpy.app.handlers.persistent
def on_blender_exit(scene=None):
    """블렌더 종료 시 렌더링이 진행 중이었다면 강제 종료 기록 (C++의 Free() 대응)"""
    if state.render_active:
        handle_render_end()

# atexit을 통한 백업 처리 (핸들러 지원 안 하는 버전용)
atexit.register(handle_render_end)


# ── Registration ──────────────────────────────────────────────────────────────

classes = (
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
        
    handlers = [
        (bpy.app.handlers.render_init, on_render_init),
        (bpy.app.handlers.render_pre, on_render_pre),
        (bpy.app.handlers.render_post, on_render_post),
        (bpy.app.handlers.render_write, on_render_write),
        (bpy.app.handlers.render_stats, on_render_stats_update),
        (bpy.app.handlers.render_complete, on_render_complete),
        (bpy.app.handlers.render_cancel, on_render_cancel),
    ]
    
    # exit_pre 핸들러는 최신 블렌더(4.2+)에서만 지원하므로 속성 확인 후 등록
    if hasattr(bpy.app.handlers, "exit_pre"):
        handlers.append((bpy.app.handlers.exit_pre, on_blender_exit))
    
    for handler_list, func in handlers:
        if func not in handler_list:
            handler_list.append(func)

def unregister():
    # 언레지스터 시에도 진행 중인 렌더가 있다면 종료 처리 (C++의 Free() 대응)
    if state.render_active:
        handle_render_end()
        
    handlers = [
        (bpy.app.handlers.render_init, on_render_init),
        (bpy.app.handlers.render_pre, on_render_pre),
        (bpy.app.handlers.render_post, on_render_post),
        (bpy.app.handlers.render_write, on_render_write),
        (bpy.app.handlers.render_stats, on_render_stats_update),
        (bpy.app.handlers.render_complete, on_render_complete),
        (bpy.app.handlers.render_cancel, on_render_cancel),
    ]
    if hasattr(bpy.app.handlers, "exit_pre"):
        handlers.append((bpy.app.handlers.exit_pre, on_blender_exit))

    for handler_list, func in handlers:
        if func in handler_list:
            handler_list.remove(func)
            
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

if __name__ == "__main__":
    register()
