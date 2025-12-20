# ==========================================
# [시온이네 일기장] V78 (Alignment & Contrast)
# ==========================================
# 1. [Alignment] 격자선(Grid)을 왼쪽 끝(0px)으로 복귀시켜 날짜 헤더와 정렬 맞춤
#    대신 이벤트 박스만 오른쪽으로 5% 밀어서 시간 숫자 공간 확보
# 2. [Legend] 범례 순서를 사용자 입력 순서(final_ids)와 동일하게 강제 정렬
# 3. [Contrast] 격자선(#ccc)과 시간 숫자(#666, #000)를 훨씬 진하게 변경
# 4. [유지] V77의 스마트 줄바꿈, 7.5pt 폰트 등 모든 기능

import streamlit as st
from weasyprint import HTML, CSS
from weasyprint.text.fonts import FontConfiguration
from google.oauth2 import service_account
from googleapiclient.discovery import build
from datetime import datetime, timedelta, date, timezone
import math

# --- [0. 페이지 설정] ---
st.set_page_config(
    page_title="시온이네 일기장 인쇄소",
    page_icon="📖",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- [1. 스타일 꾸미기] ---
st.markdown("""
    <style>
    .stApp { background-color: #FDFCF0; }
    section[data-testid="stSidebar"] { background-color: #F7F5E6; }
    .stButton > button {
        background-color: #FF4B4B;
        color: white;
        font-weight: bold;
        border-radius: 10px;
        border: none;
    }
    .stButton > button:hover {
        background-color: #FF2B2B;
        color: white;
    }
    </style>
""", unsafe_allow_html=True)

# --- [2. 인증 설정] ---
def get_calendar_service():
    try:
        service_account_info = st.secrets["google_service_account"]
        creds = service_account.Credentials.from_service_account_info(
            service_account_info,
            scopes=['https://www.googleapis.com/auth/calendar.readonly']
        )
        robot_email = service_account_info.get("client_email", "알 수 없음")
        return build('calendar', 'v3', credentials=creds), robot_email
    except Exception as e:
        st.error(f"인증 오류: Secrets 설정을 확인해주세요.\n{e}")
        return None, None

# --- [3. 색상 변환기] ---
def normalize_color(color_input):
    color_input = color_input.strip().lower()
    colors = {
        'red': '#FF0000', 'green': '#008000', 'blue': '#0000FF',
        'yellow': '#FFFF00', 'orange': '#FFA500', 'purple': '#800080',
        'pink': '#FFC0CB', 'black': '#000000', 'white': '#FFFFFF',
        'brown': '#A52A2A', 'gray': '#808080', 'grey': '#808080',
        'cyan': '#00FFFF', 'magenta': '#FF00FF', 'lime': '#00FF00',
        'olive': '#808000', 'maroon': '#800000', 'navy': '#000080',
        'teal': '#008080', 'silver': '#C0C0C0', 'gold': '#FFD700'
    }
    if color_input in colors: return colors[color_input]
    if all(c in '0123456789abcdef' for c in color_input) and len(color_input) in [3, 6]:
        return f"#{color_input}"
    return color_input

# --- [4. 로직] ---
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

def get_events_from_ids(service, target_ids, custom_colors, start_date, end_date):
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
            
            if cal_id in custom_colors:
                default_color = custom_colors[cal_id]
            else:
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
            log_msg.append(f"❌ [{cal_id}] 접근 불가: 로봇 공유 확인 필요")
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
        cluster_sorted = sorted(cluster, key=lambda x: (x['_s'], -x['_dur']))
        lanes = [] 
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

# --- [5. PDF 생성] ---
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

# [V78] ordered_ids 인자 추가 (순서 보장을 위해)
def generate_day_html(target_date, data, cal_legend_info, ordered_ids):
    allday = data['allday']
    timed = data['timed']
    if not allday and not timed: return ""
    weekday_kr = ['월', '화', '수', '목', '금', '토', '일']
    date_str = f"{target_date.strftime('%Y-%m-%d')} ({weekday_kr[target_date.weekday()]})"
    
    COL_HEIGHT = 880 
    PIXELS_PER_MIN = COL_HEIGHT / 1440
    TOP_OFFSET = 10
    
    # [V78] Legend 순서 정렬
    used_cal_ids = set()
    for evt in allday + timed: used_cal_ids.add(evt.get('calendar_id'))
    
    legend_html = "<div class='legend-container'>"
    # 순서가 보장된 ordered_ids를 순회하며 존재하는 것만 출력
    for cal_id in ordered_ids:
        if cal_id in used_cal_ids:
            info = cal_legend_info.get(cal_id)
            if info: 
                legend_html += f"<div class='legend-row'><span class='legend-box' style='background-color:{info['color']}'></span><span class='legend-text'>{info['name']}</span></div>"
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
        
        visual_duration = max(e_min - s_min, 30)
        item.update({
            '_s': s_min,
            '_e': s_min + visual_duration, 
            '_dur': visual_duration
        })
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
        
        # [V78] 격자선 진하게(#ccc), 왼쪽 끝(0px)부터 시작
        html += f"<div class='grid-line' style='top:{top}px; left:0; width:100%; height:1px; background-color:#ccc;'></div>"
        
        label_top = top - 7
        if h == 24: label_top = top - 10
        
        # [V78] 시간 숫자 진하게, 위치 조정 (왼쪽 끝)
        if h % 3 == 0 or h == 24: 
             # 3시간 단위: 완전 검정(#000), 굵게
             html += f"<div class='time-label' style='top:{label_top}px; left:0; width:30px; color:#000; font-weight:bold;'>{h}</div>"
        else:
             # 일반 시간: 진한 회색(#666)
             html += f"<div class='time-label' style='top:{label_top}px; left:0; width:30px; font-size: 6pt; color:#666;'>{h}</div>"

    for item in timeline_items:
        # [V78] 이벤트 박스 위치 계산 (Gutter 5% 적용)
        # 100% 공간 중 왼쪽 5%는 숫자 공간으로 비워둠
        GUTTER_PCT = 5.0
        
        # 원래 width(0~100)를 남은 95% 공간에 맞춰 축소
        w_pct = item['width'] * (100 - GUTTER_PCT) / 100
        
        # 원래 left(0~100)를 95% 공간으로 축소하고, 5%만큼 오른쪽으로 이동
        l_pct = GUTTER_PCT + (item['left'] * (100 - GUTTER_PCT) / 100)
        
        top_px = (item['_s'] * PIXELS_PER_MIN) + TOP_OFFSET
        font_size = get_scaled_size(7.5)
        line_height = '1.2'
        
        if item['_dur'] <= 30:
            wrap_style = "white-space: nowrap; overflow: hidden; text-overflow: ellipsis;"
        else:
            wrap_style = "white-space: normal; overflow: hidden;"
        
        html += f"<div class='event-block' style='top:{top_px}px; height:{item['_dur']*PIXELS_PER_MIN}px; left:{l_pct}%; width:{w_pct}%; background-color:{item['bg']}40; border-left:3px solid {item['bg']}; color:#333; font-size:{font_size}; line-height:{line_height}; {wrap_style}'><b>{item['summary']}</b></div>"
    
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

# [V78] create_full_pdf에 ordered_ids 인자 추가
def create_full_pdf(daily_data, cal_legend_info, ordered_ids):
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
        
        /* [V78] Grid Line CSS 수정: 기본 스타일 제거, 인라인에서 제어 */
        .time-label {{ position: absolute; text-align: right; padding-right: 5px; z-index: 1; }}
        
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
    
    full_html = "<html><body>"
    # [V78] generate_day_html에 ordered_ids 전달
    for d, events in sorted(daily_data.items()):
        full_html += generate_day_html(d, events, cal_legend_info, ordered_ids)
    full_html += "</body></html>"
    
    return HTML(string=full_html).write_pdf(stylesheets=[CSS(string=css_style, font_config=font_config)], font_config=font_config)

# --- [6. Main UI] ---
if 'pdf_data' not in st.session_state: st.session_state['pdf_data'] = None

st.title("📝 시온이네 일기장 인쇄소")

service, robot_email = get_calendar_service()

if service:
    with st.sidebar:
        st.header("⚙️ 설정")
        font_option = st.selectbox("텍스트 크기", ["보통", "작게", "크게"], index=0)
        if font_option == "작게": FONT_SCALE = 0.9
        elif font_option == "크게": FONT_SCALE = 1.1
        else: FONT_SCALE = 1.0
        
        st.divider()
        st.info(f"🤖 **이 로봇을 캘린더에 초대하세요:**")
        st.code(robot_email, language="text")
        
        st.divider()
        st.markdown("**👇 캘린더 ID 입력** (콤마로 구분, `| 색상` 옵션)")
        manual = st.text_area("ID 목록", height=120, help="예: abc@group... | red")
        
    col1, col2 = st.columns(2)
    with col1:
        start_d = st.date_input("시작 날짜", date.today())
    with col2:
        end_d = st.date_input("종료 날짜", date.today())

    if (end_d - start_d).days > 100:
        st.warning("⚠️ 기간이 너무 깁니다(100일 초과). 서버 메모리 부족으로 멈출 수 있습니다.")

    if st.button("🚀 일기책 만들기", type="primary"):
        raw_inputs = [x.strip() for x in manual.split(',') if x.strip()]
        final_ids = []
        custom_colors = {}
        for item in raw_inputs:
            if "|" in item:
                parts = item.split("|", 1)
                cid = parts[0].strip()
                color_input = parts[1].strip()
                final_color = normalize_color(color_input)
                final_ids.append(cid)
                custom_colors[cid] = final_color
            else:
                final_ids.append(item)
        
        if not final_ids: st.error("캘린더 ID를 입력해주세요!")
        elif start_d > end_d: st.error("날짜 선택이 잘못되었습니다.")
        else:
            with st.spinner("🔥 열심히 굽는 중... (잠시만 기다려주세요)"):
                daily_data, cal_legend_info, logs = get_events_from_ids(service, final_ids, custom_colors, start_d, end_d)
                
                with st.expander("🔎 처리 결과 로그"):
                    for log in logs:
                        if "❌" in log: st.error(log)
                        elif "⚠️" in log: st.warning(log)
                        else: st.success(log)
                
                total_count = sum(len(v['allday']) + len(v['timed']) for v in daily_data.values())
                if total_count == 0:
                    st.warning("가져온 일기가 없습니다.")
                else:
                    # [V78] final_ids(순서 있는 리스트) 전달
                    pdf_bytes = create_full_pdf(daily_data, cal_legend_info, final_ids)
                    st.session_state['pdf_data'] = pdf_bytes
                    st.balloons()
                    st.success(f"완성! 총 {total_count}개의 일기를 담았습니다.")

    if st.session_state['pdf_data']:
        st.download_button("📥 PDF 다운로드", st.session_state['pdf_data'], file_name="MyDiary.pdf")
else:
    st.error("인증 정보를 불러오지 못했습니다.")
