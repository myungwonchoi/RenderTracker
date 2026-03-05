import json
import os
import requests
import time
from constants import DISCORD_COOLDOWN_SEC

# 내부 쿨타임 관리 변수
_last_progress_ts = 0

def send_discord(url, embed, uid="", mention=False, file_path=None):
    if not url: return None
    try:
        body = {"embeds": [embed]}
        if mention and uid: body["content"] = f"<@{uid}>"
        
        files = None
        if file_path and os.path.exists(file_path):
            # 파일이 있으면 attachment: 루틴 사용
            fname = os.path.basename(file_path)
            embed["image"] = {"url": f"attachment://{fname}"}
            files = {"file": (fname, open(file_path, "rb"))}
            # 파일과 함께 보낼 때는 payload_json 형식을 사용해야 함
            r = requests.post(url + "?wait=true", data={"payload_json": json.dumps(body)}, files=files, timeout=15)
        else:
            r = requests.post(url + "?wait=true", json=body, timeout=10)

        if r.status_code in (200, 201): return r.json().get("id")
    except Exception: pass
    return None

def patch_discord(url, mid, embed, file_path=None):
    if not url or not mid: return
    try:
        # attachments: [] 를 지정하여 기존에 업로드된 파일들을 모두 제거하고 새 파일을 올립니다.
        body = {"embeds": [embed], "attachments": []}
        files = None
        if file_path and os.path.exists(file_path):
            fname = os.path.basename(file_path)
            embed["image"] = {"url": f"attachment://{fname}"}
            files = {"file": (fname, open(file_path, "rb"))}
            # 파일과 함께 보낼 때는 payload_json 형식을 사용해야 함
            requests.patch(f"{url}/messages/{mid}", data={"payload_json": json.dumps(body)}, files=files, timeout=15)
        else:
            requests.patch(f"{url}/messages/{mid}", json={"embeds":[embed]}, timeout=10)
    except Exception: pass

def embed(title, desc, color, fields=None):
    e = {"title": title, "description": desc, "color": color}
    if fields: e["fields"] = fields
    return e

def fmt_time_discord(s):
    if s is None or s < 0:
        return "—"
    m, s = divmod(int(s), 60)
    h, m = divmod(m, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"

def notify_started(init, cfg, msgs):
    doc=init.get("doc_name",""); rs=init.get("render_setting",""); pc=cfg.get("pc_name","")
    rx=init.get("res_x",0); ry=init.get("res_y",0); sf=init.get("start_frame",0)
    ef=init.get("end_frame",0); tot=init.get("total_frames",0)
    path=init.get("output_path",""); st=init.get("start_time","")
    t=msgs.get("render_started_title","Render Started [{doc_name}] - [{render_setting}]")
    t=t.replace("{doc_name}",doc).replace("{render_setting}",rs)
    sw=init.get("software","C4D"); rn=init.get("renderer",rs)
    d=msgs.get("render_started_desc","-# PC: {pc_name}").replace("{pc_name}",pc)
    f=[{"name":msgs.get("ui_software","Software"),"value":f"`{sw}`","inline":True},
       {"name":msgs.get("ui_renderer","Renderer"),"value":f"`{rn}`","inline":True},
       {"name":"\u200b","value":"\u200b","inline":True},
       {"name":msgs.get("field_resolution","Resolution"),"value":f"`{rx}x{ry}`","inline":True},
       {"name":msgs.get("field_frame_range","Frame Range"),"value":f"`{sf}~{ef} ({tot}f)`","inline":True},
       {"name":"\u200b","value":"\u200b","inline":True},
       {"name":msgs.get("field_start_time","Start Time"),"value":f"`{st}`","inline":False},
       {"name":msgs.get("field_render_path","Output Path"),"value":f"`{path}`","inline":False}]
    global _last_progress_ts
    _last_progress_ts = 0 # 새로운 세션 시작 시 즉시 업데이트 가능하도록 초기화
    return send_discord(cfg.get("webhook_url",""), embed(t,d,0x22c55e,f), cfg.get("discord_userid",""), cfg.get("use_mention",False))

def notify_progress(init, upd, cfg, msgs, pmid, thumb_path=None, force=False):
    global _last_progress_ts
    now = time.time()
    if not force and (now - _last_progress_ts < DISCORD_COOLDOWN_SEC):
        return pmid # 쿨타임 미충족 시 전송 스킵
    
    _last_progress_ts = now
    doc=init.get("doc_name",""); rs=init.get("render_setting",""); pc=cfg.get("pc_name","")
    tot=init.get("total_frames",1); ren=upd.get("rendered_frames",0)
    curr_f=upd.get("current_frame", 0)
    el=upd.get("elapsed_seconds",0); rem=upd.get("remaining_seconds",-1)
    avg=upd.get("avg_frame_duration",0); lf=upd.get("last_frame_duration",0)
    cft_time=upd.get("field_current_frame_time","—")
    t=msgs.get("rendering_progress_title","Rendering... [{doc_name}] - [{render_setting}]")
    t=t.replace("{doc_name}",doc).replace("{render_setting}",rs)
    sw=init.get("software","C4D"); rn=init.get("renderer",rs)
    prog = min(int(ren/tot*20), 20) if tot > 0 else 0
    bar = "🟩" * prog + "⬜" * (20 - prog)
    d=msgs.get("rendering_progress_desc","{progress_bar}\n\n-# PC: {pc_name}")
    d=d.replace("{progress_bar}",bar).replace("{pc_name}",pc)
    eta=time.strftime('%Y-%m-%d %H:%M:%S',time.localtime(time.time()+rem)) if rem>=0 else "—"
    f=[{"name":msgs.get("ui_software","Software"),"value":f"`{sw}`","inline":True},
       {"name":msgs.get("ui_renderer","Renderer"),"value":f"`{rn}`","inline":True},
       {"name":"\u200b","value":"\u200b","inline":True},
       {"name":msgs.get("field_current_frame_status","Frame"),"value":f"`{curr_f}`","inline":True},
       {"name":msgs.get("field_progress","Progress"),"value":f"`{ren}/{tot}`","inline":True},
       {"name":"\u200b","value":"\u200b","inline":True},
       {"name":msgs.get("field_current_frame_time","Current"),"value":f"`{cft_time}`","inline":True},
       {"name":msgs.get("field_last_frame","Last"),"value":f"`{fmt_time_discord(lf)}`","inline":True},
       {"name":msgs.get("field_average","Avg"),"value":f"`{fmt_time_discord(avg)}`","inline":True},
       {"name":msgs.get("field_elapsed","Elapsed"),"value":f"`{fmt_time_discord(el)}`","inline":True},
       {"name":msgs.get("field_remaining","Remaining"),"value":f"`{fmt_time_discord(rem)}`","inline":True},
       {"name":msgs.get("field_eta","ETA"),"value":f"`{eta}`","inline":True}]
    
    e2=embed(t,d,0xeab308,f); wh=cfg.get("webhook_url","")
    # 최적화된 썸네일 경로만 사용 (리소스 절약 위해 원본 경로는 무시)
    img_path = thumb_path if (thumb_path and os.path.exists(thumb_path)) else None

    if pmid: 
        patch_discord(wh, pmid, e2, file_path=img_path)
        return pmid
    return send_discord(wh, e2, cfg.get("discord_userid",""), cfg.get("use_mention",False), file_path=img_path)

def notify_finished(init, upd, end, cfg, msgs, is_fin, pmid=None, thumb_path=None):
    # 완료/중지 메시지를 보내기 전에 마지막으로 진행률을 100%(혹은 최종 상태)로 업데이트
    if pmid:
        notify_progress(init, upd, cfg, msgs, pmid, thumb_path=thumb_path, force=True) # 종료 시에는 쿨타임 무시하고 강제 업데이트
        time.sleep(1) # 디스코드 업데이트 순서 보장을 위한 미세 지연

    doc=init.get("doc_name",""); rs=init.get("render_setting",""); pc=cfg.get("pc_name","")
    tot=init.get("total_frames",0); ren=upd.get("rendered_frames",0)
    el=upd.get("elapsed_seconds",0); path=init.get("output_path","")
    st=init.get("start_time",""); et=end.get("end_time","")
    tk=("render_finished_title" if is_fin else "render_stopped_title")
    col=0x3b82f6 if is_fin else 0xef4444
    t=msgs.get(tk,"Render Finished").replace("{doc_name}",doc).replace("{render_setting}",rs)
    sw=init.get("software","C4D"); rn=init.get("renderer",rs)
    d=msgs.get("render_finished_desc","-# PC: {pc_name}").replace("{pc_name}",pc)
    f=[{"name":msgs.get("ui_software","Software"),"value":f"`{sw}`","inline":True},
       {"name":msgs.get("ui_renderer","Renderer"),"value":f"`{rn}`","inline":True},
       {"name":"\u200b","value":"\u200b","inline":True},
       {"name":msgs.get("field_total_elapsed","Total"),"value":f"`{fmt_time_discord(el)}`","inline":True},
       {"name":msgs.get("field_start_time","Start"),"value":f"`{st}`","inline":True},
       {"name":msgs.get("field_end_time","End"),"value":f"`{et}`","inline":True},
       {"name":msgs.get("field_progress","Progress"),"value":f"`{ren}/{tot}`","inline":False},
       {"name":msgs.get("field_render_path","Output"),"value":f"`{path}`","inline":False}]
    
    send_discord(cfg.get("webhook_url", ""), embed(t, d, col, f), cfg.get("discord_userid", ""), cfg.get("use_mention", False))

def notify_crash(init, upd, cfg, msgs):
    ren=upd.get("rendered_frames",0); tot=init.get("total_frames",0); path=init.get("output_path","")
    sw=init.get("software","C4D"); rn=init.get("renderer","—")
    t=msgs.get("crash_title","C4D Crashed!"); d=msgs.get("crash_desc","Cinema 4D closed unexpectedly.")
    f=[{"name":msgs.get("ui_software","Software"),"value":f"`{sw}`","inline":True},
       {"name":msgs.get("ui_renderer","Renderer"),"value":f"`{rn}`","inline":True},
       {"name":"\u200b","value":"\u200b","inline":True},
       {"name":msgs.get("field_current_frame_status","Last Frame"),"value":f"`{ren}/{tot}`","inline":True},
       {"name":msgs.get("field_render_path","Output"),"value":f"`{path}`","inline":False}]
    send_discord(cfg.get("webhook_url",""),embed(t,d,0xef4444,f),cfg.get("discord_userid",""),cfg.get("use_mention",False))
