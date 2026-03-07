bl_info = {
    "name": "RenderTracker (Blender)",
    "description": "Sends render status to RenderTracker via socket.",
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
import atexit
import socket

# 전역 상태 변수
class RenderState:
    render_start_ts = 0.0
    render_start_time = 0.0
    last_frame_time = 0.0
    frame_start_time = 0.0
    total_frame_duration = 0.0
    completed_frames_count = 0
    current_frame = 0
    total_frames = 1
    doc_name = "Untitled"
    res_x = 0
    res_y = 0
    start_frame = 0
    end_frame = 0
    output_path = ""
    last_frame_duration = 0.0
    last_frame_image_path = ""
    first_frame_image_path = ""
    first_frame_saved = False
    render_active = False # 렌더링 활성 상태 플래그

state = RenderState()


def send_render_status(last_frame_duration, current_frame_start_ts, last_rendered_image_path, end_ts, event="PROGRESS"):
    """DCC 상태 데이터를 구성하여 소켓으로 전송합니다."""
    data = {
        "event": event,
        "start": {
            "start_ts": state.render_start_ts,
            "dcc_pid": os.getpid(),
            "doc_name": state.doc_name,
            "take_name": None,
            "render_setting": None,
            "res_x": state.res_x,
            "res_y": state.res_y,
            "start_frame": state.start_frame,
            "end_frame": state.end_frame,
            "total_frames": state.total_frames,
            "output_path": state.output_path,
            "software": "Blender",
            "renderer": "Blender Render",
            "last_frame_path": state.last_frame_image_path,
            "first_frame_path": state.first_frame_image_path
        },
        "update": {
            "rendered_frames": state.completed_frames_count,
            "current_frame": state.current_frame,
            "last_frame_duration": last_frame_duration,
            "current_frame_start_ts": current_frame_start_ts,
            "last_rendered_image_path": last_rendered_image_path
        },
        "end": {
            "end_ts": end_ts
        }
    }

    # 소켓으로 데이터 전송
    send_status_socket(data)

def send_status_socket(data):
    """로컬 서버(50000번 포트)로 데이터를 전송합니다."""
    try:
        message = json.dumps(data, ensure_ascii=False)
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.5)
            s.connect(('127.0.0.1', 50000))
            s.sendall(message.encode('utf-8'))
    except Exception:
        pass


@bpy.app.handlers.persistent
def on_render_write(scene):
    """프레임 저장이 완료된 시점에 호출됩니다."""
    if not state.render_active: return
    
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
        
    state.last_frame_image_path = raw_path
    state.current_frame = scene.frame_current
    
    send_render_status_from_state(event="PROGRESS")

def send_render_status_from_state(event="PROGRESS"):
    """현재 state 정보를 바탕으로 상태 전송"""
    send_render_status(state.last_frame_duration, state.frame_start_time, state.last_frame_image_path, -1.0, event=event)


# ── Handlers ──────────────────────────────────────────────────────────────────

@bpy.app.handlers.persistent
def on_render_init(scene):
    now = time.time()
    state.render_start_time = now
    state.render_start_ts = now
    state.last_frame_time = now
    state.total_frame_duration = 0.0
    state.completed_frames_count = 0
    state.frame_start_time = now
    state.current_frame = 0
    state.last_frame_image_path = ""
    state.first_frame_image_path = ""
    state.first_frame_saved = False
    state.render_active = True

    # Scene info collection
    state.doc_name = bpy.data.filepath.split("\\")[-1].split("/")[-1] if bpy.data.filepath else "Untitled"
    state.res_x = int(scene.render.resolution_x * (scene.render.resolution_percentage / 100.0))
    state.res_y = int(scene.render.resolution_y * (scene.render.resolution_percentage / 100.0))
    state.start_frame = scene.frame_start
    state.end_frame = scene.frame_end
    state.total_frames = (state.end_frame - state.start_frame) + 1 if state.end_frame >= state.start_frame else 1
    state.output_path = os.path.dirname(bpy.path.abspath(scene.render.frame_path(frame=scene.frame_start)))

    send_render_status(0.0, state.frame_start_time, "", -1.0, event="START")


@bpy.app.handlers.persistent
def on_render_pre(scene):
    now = time.time()
    last_interval = 0.0
    if state.current_frame > 0:
        last_interval = now - state.last_frame_time
        
    state.last_frame_time = now
    state.frame_start_time = now
    state.current_frame = scene.frame_current

    send_render_status(last_interval, state.frame_start_time, state.last_frame_image_path, -1.0, event="PROGRESS")


@bpy.app.handlers.persistent
def on_render_post(scene):
    now = time.time()
    current_frame_active_duration = now - state.frame_start_time
    state.last_frame_duration = current_frame_active_duration
    state.total_frame_duration += current_frame_active_duration
    state.completed_frames_count += 1
    
    send_render_status(current_frame_active_duration, state.frame_start_time, state.last_frame_image_path, -1.0, event="PROGRESS")


@bpy.app.handlers.persistent
def on_render_complete(scene):
    handle_render_end(event="FINISH")

@bpy.app.handlers.persistent
def on_render_cancel(scene):
    handle_render_end(event="STOP")

def handle_render_end(event="FINISH"):
    if not state.render_active:
        return
        
    state.render_active = False
    send_render_status(state.last_frame_duration, state.frame_start_time, state.last_frame_image_path, time.time(), event=event)

@bpy.app.handlers.persistent
def on_blender_exit(scene=None):
    if state.render_active:
        handle_render_end()

atexit.register(handle_render_end)


# ── Registration ──────────────────────────────────────────────────────────────

def register():
    handlers = [
        (bpy.app.handlers.render_init, on_render_init),
        (bpy.app.handlers.render_pre, on_render_pre),
        (bpy.app.handlers.render_post, on_render_post),
        (bpy.app.handlers.render_write, on_render_write),
        (bpy.app.handlers.render_complete, on_render_complete),
        (bpy.app.handlers.render_cancel, on_render_cancel),
    ]
    
    if hasattr(bpy.app.handlers, "exit_pre"):
        handlers.append((bpy.app.handlers.exit_pre, on_blender_exit))
    
    for handler_list, func in handlers:
        if func not in handler_list:
            handler_list.append(func)

def unregister():
    if state.render_active:
        handle_render_end()
        
    handlers = [
        (bpy.app.handlers.render_init, on_render_init),
        (bpy.app.handlers.render_pre, on_render_pre),
        (bpy.app.handlers.render_post, on_render_post),
        (bpy.app.handlers.render_write, on_render_write),
        (bpy.app.handlers.render_complete, on_render_complete),
        (bpy.app.handlers.render_cancel, on_render_cancel),
    ]
    if hasattr(bpy.app.handlers, "exit_pre"):
        handlers.append((bpy.app.handlers.exit_pre, on_blender_exit))

    for handler_list, func in handlers:
        if func in handler_list:
            handler_list.remove(func)

if __name__ == "__main__":
    register()
