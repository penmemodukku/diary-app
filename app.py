# ==========================================
# [시온이네 일기장] V66 (Bug Fix)
# ==========================================
# 1. [Fix] create_full_pdf 함수 내 'font_config' 정의 누락 수정 (NameError 해결)
# 2. [유지] V65의 모든 기능 (멀티 캘린더, 로봇 안내, 폰트 조절, 레이아웃)

import streamlit as st
from weasyprint import HTML, CSS
from weasyprint.text.fonts import FontConfiguration
from google.oauth2 import service_account
from googleapiclient.discovery import build
from datetime import datetime, timedelta, date, timezone
import math

# --- [1. 인증 설정 및 로봇 정보 획득] ---
def get_calendar_service():
    try:
        service_account_info = st.secrets["google_service_account"]
        creds = service_account.Credentials.from_service_account_info(
            service_account_info,
            scopes=['https://www.googleapis.com/auth/calendar.readonly']
        )
        # 로봇 이메일 주소 추출 (화면 표시용)
        robot_email = service_account_info.get("client_email", "알 수 없음")
        return build('calendar', 'v3', credentials=creds), robot_email
    except Exception as e:
        st.error(f"인증 오류: Secrets 설정을 확인해주세요.\n{e}")
        return None, None

# --- [2. 로직] ---
KST = timezone(timedelta(hours=9))

def force_break_text(text):
    if not text: return ""
    chunk_size = 15
    return '<wbr>'.join([text[i:i+chunk_size] for i in range(0, len(text), chunk_size)])

def get_google_colors(service):
    try:
        colors = service.colors().get().execute()
        return colors.get('calendar', {}), colors.get('event', {})
    except:
        return {}, {}

def get_events_from_ids(service, target_ids, start_date, end_date):
    if not target_ids: return {}, {}, ["❌ 캘린더 ID를 입력해주세요."]
    
    cal_colors_map, event_colors_map = get_google_colors(service)
    
    start_dt = datetime.combine(start_date, datetime.min.time()) - timedelta(days=1)
    end_dt = datetime.combine(end_date, datetime.max.time()) + timedelta(days=1)
    time_min = start_dt.isoformat() + 'Z'
    time_max = end_dt.isoformat() + 'Z'

    all_events = []
    log_msg = []
    
    cal_legend_info = {}

    for cal_id in target_ids:
        cal_id = cal_id.strip() 
        if not cal_id: continue
        
        try:
            cal_info = service.calendars().get(calendarId=cal_id).execute()
            cal_name = cal_info.get('summary', cal_id)
            cal_color_id = cal_info.get('colorId', '1') 
            default_color = cal_colors_map.get(cal_color_id, {'background': '#a4bdfc'})['background']
            cal_legend_info[cal_id] = {'name': cal_name, 'color': default_color}

            events_result = service.events().list(
                calendarId=cal_id, timeMin=time_min, timeMax=time_max,
                maxResults=2500, singleEvents=True, orderBy='startTime'
            ).execute()
            
            items = events_result.get('items', [])
            if items:
                for event in items:
                    event['calendar_id'] = cal_id
                    event['calendar_name'] = cal_name
                    evt_color_id = event.get('colorId')
                    if evt_color_id and evt_color_id in event_colors_map:
                        event['real_color'] = event_colors_map[evt_color_id]['background']
                    else:
                        event['real_color'] = default_color
                    all_events.append(event)
                log_msg.append(f"✅ [{cal_name}] : {len(items)}개")
            else:
                log_msg.append(f"⚠️ [{cal_name}] : 일정 없음")
                
        except Exception as e:
            log_msg.append(f"❌ [{cal_id}] 접근 불가: 로봇에게 공유되었나요?")
            continue

    daily_groups = {}
    curr = start_date
    while curr <= end_date:
        daily_groups[curr] = {'allday': [], 'timed': []}
        curr += timedelta(days=1)

    for event in all_events:
        start = event['start']
        if 'date' in start:
            try:
                evt_date = datetime.strptime(start['date'], '%Y-%m-%d').date()
                if start_date <= evt_date <= end_date:
                    daily_groups[evt_date]['allday'].append(event)
            except: pass
        elif 'dateTime' in start:
            try:
                dt_obj = datetime.fromisoformat(start['dateTime'].replace('Z', '+00:00'))
                dt_kst = dt_obj.astimezone(KST)
                event['dt_object'] = dt_kst
                evt_date = dt_kst.date()
                if start_date <= evt_date <= end_date:
                    daily_groups[evt_date]['timed'].append(event)
            except: pass
            
    for d in daily_groups:
        daily_groups[d]['timed'].sort(key=lambda x: x['dt_object'])
            
    return daily_groups, cal_legend_info, log_msg

def calculate_visual_layout(events):
    if not events: return []
    sorted_events = sorted(events, key=lambda x: x['_s'])
    clusters = []
    if not sorted_events: return []
    current_cluster = [sorted_events[0]]
    cluster_end = sorted_events[0]['_e']
    for i in range(1, len(sorted_events)):
        evt = sorted_events[i]
        if evt['_s'] < cluster_end:
            current_cluster.append(evt)
            cluster_end = max(cluster_end, evt['_e'])
        else:
            clusters.append(current_cluster)
            current_cluster = [evt]
            cluster_end = evt['_e']
    clusters.append(current_cluster)
    final_items = []
    for cluster in clusters:
        lanes = []
        cluster_sorted = sorted(cluster, key=lambda x: (x['_s'], -x['_dur']))
        for evt in cluster_sorted:
            placed = False
            for lane in lanes:
                last_evt = lane[-1]
                if evt['_s'] >= last_evt['_e']:
                    lane.append(evt)
                    placed = True
                    break
            if not placed:
                lanes.append([evt])
        total_lanes = len(lanes)
        for i, lane in enumerate(lanes):
            for evt in lane:
                evt['width'] = 100 / total_lanes
                evt['left'] = i * (100 / total_lanes)
                final_items.append(evt)
    return final_items

def get_time_info(event):
    start_dt = event['dt_object']
    end_dt = datetime.fromisoformat(event['end'].get('dateTime').replace('Z', '+00:00')).astimezone(KST)
    time_range = f"{start_dt.strftime('%H:%M')} - {end_dt.strftime('%H:%M')}"
    duration = end_dt - start_dt
    total_seconds = int(duration.total_seconds())
    h, r = divmod(total_seconds, 3600)
    m = r // 60
    dur_str = []
    if h > 0: dur_str.append(f"{h}h")
    if m > 0: dur_str.append(f"{m}m")
    if not dur_str: dur_str.append("0m")
    return time_range, " ".join(dur_str)

# --- [3. PDF 생성] ---
FONT_SCALE = 1.0

def get_scaled_size(pt):
    return f"{pt * FONT_SCALE}pt"

def estimate_height(desc, is_title=False):
    if not desc: return 0
    lines = desc.count('\\n') + 1
    chars_per_line = 40 / FONT_SCALE 
    lines += len(desc) / chars_per_line
    base = 25 if is_title else 0 
    line_height = 16 * FONT_SCALE
    return base + (lines * line_height) + 10 

def generate_day_html(target_date, data, cal_legend_info):
    allday = data['allday']
    timed = data['timed']
    if not allday and not timed: return ""
    weekday_kr = ['월', '화', '수', '목', '금', '토', '일']
    date_str = f"{target_date.strftime('%Y-%m-%d')} ({weekday_kr[target_date.weekday()]})"
    
    COL_HEIGHT = 880 
    PIXELS_PER_MIN = COL_HEIGHT / 1440
    TOP_OFFSET = 10
    
    used_cal_ids = set()
    for evt in allday + timed: used_cal_ids.add(evt.get('calendar_id'))
    legend_html = "<div class='legend-container'>"
    for cal_id in used_cal_ids:
        info = cal_legend_info.get(cal_id)
        if info: legend_html += f"<div class='legend-row'><span class='legend-box' style='background-color:{info['color']}'></span><span class='legend-text'>{info['name']}</span></div>"
    legend_html += "</div>"

    visual_events = []
    for evt in timed:
        start = evt['dt_object']
        end = datetime.fromisoformat(evt['end'].get('dateTime').replace('Z', '+00:00')).astimezone(KST)
        s_min = start.hour * 60 + start.minute
        e_min = end.hour * 60 + end.minute
        if e_min > 1440: e_min = 1440 
        real_color = evt.get('real_color', '#cccccc')
        item = {'summary': evt.get('summary',''), 'cal': evt.get('calendar_name',''), 'bg': real_color}
        item.update({'_s': s_min, '_e': e_min, '_dur': max(e_min - s_min, 15)})
        visual_events.append(item)

    timeline_items = calculate_visual_layout(visual_events)

    html = f"""
    <div class='day-container'>
        <div class='first-page-container'>
            <div class='content-wrapper'>
                <div class='text-column'> 
                    <div class='header-wrapper'>
                        <div class='date-header'>{date_str}</div>
                        {legend_html}
                    </div>
                    <div class='header-line'></div>
                    <div class='visual-page'>
                        <div class='timeline-col'>
    """
    
    for h in range(25):
        top = (h * 60 * PIXELS_PER_MIN) + TOP_OFFSET
        html += f"<div class='grid-line' style='top:{top}px;'></div>"
        label_top = top - 7
        if h == 24: label_top = top - 10
        if h % 3 == 0 or h == 24: 
             html += f"<div class='time-label' style='top:{label_top}px;'>{h}</div>"
        else:
             html += f"<div class='time-label' style='top:{label_top}px; font-size: 6pt; color:#ccc;'>{h}</div>"

    for item in timeline_items:
        w_pct = item['width'] * 0.9 if item['width'] < 100 else 90
        l_pct = (item['left'] * 0.9) + 10 if item['width'] < 100 else 10
        top_px = (item['_s'] * PIXELS_PER_MIN) + TOP_OFFSET
        
        dur = item['_dur']
        if dur < 20: 
            font_size = get_scaled_size(5)
            line_height = '1.0' 
        elif dur < 40:
            font_size = get_scaled_size(6.5)
            line_height = '1.1'
        else:
            font_size = get_scaled_size(8.5)
            line_height = '1.2'
        
        html += f"<div class='event-block' style='top:{top_px}px; height:{item['_dur']*PIXELS_PER_MIN}px; left:{l_pct}%; width:{w_pct}%; background-color:{item['bg']}40; border-left:3px solid {item['bg']}; color:#333; font-size:{font_size}; line-height:{line_height};'><b>{item['summary']}</b></div>"
    
    html += """
                        </div>
                    </div> 
                </div> 
                <div class='memo-column'></div>
            </div>
        </div> 
    """
    
    text_items_flat = []
    for evt in allday: evt['is_allday'] = True; text_items_flat.append(evt)
    for evt in timed: evt['is_allday'] = False; text_items_flat.append(evt)
    
    if text_items_flat:
        html += f"""
        <div class='content-wrapper text-pages-wrapper'>
            <div class='text-column'>
                <div class='date-header-manual'>{date_str} (계속)</div>
        """
        for evt in text_items_flat:
            raw_desc = evt.get('description','') or ''
            clean_desc = force_break_text(raw_desc).replace('\\n', '<br>')
            real_color = evt.get('real_color', '#333')
            if evt.get('is_allday'):
                title_html = f"<span class='text-title' style='color:{real_color};'>[종일] {evt.get('summary','')}</span>"
                html += f"""<div class='text-item'><div class='allday-styled' style='border-color:{real_color};'>{title_html}<div class='text-desc'>{clean_desc}</div></div></div>"""
            else:
                t_range, dur_str = get_time_info(evt)
                meta_html = f"<span class='text-meta'><span style='color:{real_color}; font-weight:800; margin-right:5px;'>[{evt.get('calendar_name','')}]</span>{t_range} ({dur_str})</span>"
                title_html = f"<span class='text-title' style='color:{real_color};'>{evt.get('summary','')}</span>"
                html += f"""<div class='text-item'>{meta_html}{title_html}<div class='text-desc'>{clean_desc}</div></div>"""
        html += """</div><div class='memo-column'></div></div>"""
    html += "</div>"
    return html

def create_full_pdf(daily_data, cal_legend_info):
    # [V66 Fix] font_config 정의 추가
    font_config = FontConfiguration()
    
    body_font = get_scaled_size(8.5)
    meta_font = get_scaled_size(7.5)
    title_font = get_scaled_size(10)
    
    css_style = f"""
        @page {{ size: A4; margin: 1.5cm; }}
        body {{ font-family: 'NanumGothic', sans-serif; color: #333; line-height: 1.35; font-size: {body_font}; }}
        .day-container {{ page-break-after: always; }}
        .first-page-container {{
            display: inline-block; width: 100%;
            page-break-inside: avoid; break-inside: avoid; margin-bottom: 20px;
        }}
        .header-wrapper {{ display: flex; justify-content: space-between; align-items: flex-end; margin-bottom: 5px; position: relative; z-index: 500; background-color: white;}}
        .date-header {{ font-size: 16pt; font-weight: bold; color: #3e2723; margin: 0; padding: 0; }}
        .header-line {{ width: 100%; height: 2px; background-color: #5d4037; margin-bottom: 10px; }}
        .legend-container {{ text-align: right; }}
        .legend-row {{ display: flex; align-items: center; justify-content: flex-end; margin-bottom: 2px; }}
        .legend-box {{ display: inline-block; width: 8px; height: 8px; margin-right: 5px; border-radius: 2px; border: 1px solid #ccc; }}
        .legend-text {{ font-size: 7pt; color: #666; }}
        .visual-page {{ width: 100%; height: 900px; position: relative; overflow: visible; margin-top: 5px; margin-bottom: 10px; }}
        .timeline-col {{ position: absolute; top: 10px; height: 880px; width: 100%; box-sizing: border-box; }}
        .grid-line {{ position: absolute; left: 0; width: 100%; height: 1px; background-color: #eee; z-index: 0; }}
        .time-label {{ position: absolute; left: 0; font-size: 7pt; font-weight: bold; color: #999; background-color: white; padding-right: 5px; z-index: 1; }}
        .event-block {{ position: absolute; border-radius: 2px; padding: 1px 3px; border: 1px solid white; box-shadow: 1px 1px 1px rgba(0,0,0,0.1); display: flex; flex-direction: column; justify-content: flex-start; z-index: 10; box-sizing: border-box; overflow: hidden; }}
        .date-header-manual {{ 
            font-size: 12pt; font-weight: bold; color: #5d4037; 
            border-bottom: 1px solid #ddd; padding-bottom: 5px; margin-bottom: 15px; 
            width: 100%; display: block;
            page-break-after: avoid; break-after: avoid;
        }}
        .content-wrapper {{ display: flex; width: 100%; }} 
        .text-column {{ width: 75%; padding-right: 2%; }} 
        .memo-column {{ width: 23%; }} 
        .text-item {{ 
            margin-bottom: 15px; padding-bottom: 5px; border-bottom: 1px solid #f9f9f9; width: 100%; 
            page-break-inside: auto; break-inside: auto; orphans: 1; widows: 1;
        }}
        .allday-styled {{ background-color: #fff8e1; padding: 8px; border-radius: 4px; border-left: 3px solid; }}
        .text-meta {{ display: block; font-size: {meta_font}; color: #888; font-weight: bold; margin-bottom: 1px; }}
        .text-title {{ display: block; font-size: {title_font}; font-weight: bold; margin-bottom: 3px; }}
        .text-desc {{ 
            font-size: {body_font}; color: #444; white-space: pre-wrap; line-height: 1.5; word-break: break-all; overflow-wrap: break-word; 
            break-inside: auto; 
        }}
    """
    return HTML(string=full_html).write_pdf(stylesheets=[CSS(string=css_style, font_config=font_config)], font_config=font_config)

# --- [4. UI] ---
st.set_page_config(page_title="시온이네 일기장", page_icon="📝", layout="wide")

if 'pdf_data' not in st.session_state: st.session_state['pdf_data'] = None

st.title("📝 시온이네 일기장 인쇄소 (V66)")

service, robot_email = get_calendar_service()

if service:
    with st.sidebar:
        st.header("⚙️ 설정")
        font_option = st.selectbox("텍스트 크기", ["보통", "작게", "크게"], index=0)
        if font_option == "작게": FONT_SCALE = 0.9
        elif font_option == "크게": FONT_SCALE = 1.1
        else: FONT_SCALE = 1.0
        
        st.divider()
        
        # [NEW] 로봇 정보 표시
        st.info(f"🤖 **이 로봇을 캘린더에 초대하세요:**")
        st.code(robot_email, language="text")
        st.caption("위 이메일을 복사해서 구글 캘린더 설정 > '특정 사용자와 공유'에 추가해주세요.")
        
        st.divider()
        
        manual = st.text_area(
            "캘린더 ID 입력 (콤마로 구분)", 
            height=100, 
            help="구글 캘린더 설정 > 캘린더 통합 > 캘린더 ID를 복사해서 넣으세요."
        )
        
    d = st.date_input("📅 기간 선택", [date.today(), date.today()], format="YYYY/MM/DD")

    if st.button("🚀 일기책 만들기", type="primary"):
        ids = [x.strip() for x in manual.split(',') if x.strip()]
        
        if not ids: st.error("캘린더 ID를 입력해주세요!")
        elif len(d) < 2: st.error("기간을 선택해주세요!")
        else:
            with st.spinner("데이터 처리 및 PDF 생성 중..."):
                daily_data, cal_legend_info, logs = get_events_from_ids(service, ids, d[0], d[1])
                with st.expander("🔎 처리 결과 로그 (클릭해서 확인)"):
                    for log in logs:
                        if "❌" in log: st.error(log)
                        elif "⚠️" in log: st.warning(log)
                        else: st.success(log)
                
                total_count = sum(len(v['allday']) + len(v['timed']) for v in daily_data.values())
                if total_count == 0:
                    st.warning("가져온 일기가 없습니다. ID와 공유 설정을 확인하세요.")
                else:
                    pdf_bytes = create_full_pdf(daily_data, cal_legend_info)
                    st.session_state['pdf_data'] = pdf_bytes
                    st.balloons()
                    st.success(f"완성! {total_count}개의 일기를 담았습니다.")

    if st.session_state['pdf_data']:
        st.download_button("📥 PDF 다운로드", st.session_state['pdf_data'], file_name="MyDiary_V66.pdf")
else:
    st.error("인증 정보를 불러오지 못했습니다.")
