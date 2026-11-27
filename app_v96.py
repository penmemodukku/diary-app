# V98.5.3 — 주간·월간 용지 방향 및 선택 색상 개선
# V98.5 — 월간·연간 복수 선택
# V98.4.3 — 주간 미리보기 및 선택 디자인 개선
# V98.4.1 — 주차 선택 개선
# V98.3.4 — 인쇄 날짜 기준 시간 표기 개선
# V98.3.2 — 일간 종일 일정 및 미리보기 개선
# V98.3.1 — 종일 기간 일정 개선
# V98.3 — 연간 하이라이트 및 월간 한 장 고정
# V96.4.1 — 밝은 테마 고정 + 눈에 띄는 여백 조절 + 페이지 탐색 개선
# V96.3 — 캘린더 ID 자동 불러오기
# V96.2의 PDF/2단 편집 로직은 그대로 유지하고, 사이드바 기본 입력값만 변경했습니다.
# Streamlit Cloud Secrets 예시 (실제 ID를 채워 넣으세요):
# default_calendar_ids = """calendar-id-1 | brown, calendar-id-2 | blue"""
# 주의: GitHub 공개 저장소에 실제 ID 또는 서비스 계정 비밀키를 올리지 마세요.

# ==========================================
# [시온이네 일기장] V96.2 (Two-Column + Flowing Entry Text)
# ==========================================
# 1. [Logic Fix] 날짜를 넘어가는 일정(예: 전날 23시 ~ 금일 09시)이 '오늘' 목록에도 포함되도록 로직 수정
#    -> 시작일과 종료일 사이의 모든 날짜에 이벤트를 할당 (Overlap Check)
# 2. [Visual Fix] 타임라인 그릴 때, 전날 시작된 일정은 '0시 0분'부터 시작하도록 시작점 보정 (Clamping)
# 3. [Base] V94(해시태그) 폐기하고 V93(완성형 디자인) 기반으로 작업

import streamlit as st
from weasyprint import HTML, CSS
from weasyprint.text.fonts import FontConfiguration
from google.oauth2 import service_account
from googleapiclient.discovery import build
from datetime import datetime, timedelta, date, timezone
import math
import fitz  # PyMuPDF: PDF 페이지를 이미지로 미리보기

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
    .stApp, .stApp p, .stApp label, .stApp h1, .stApp h2, .stApp h3, .stApp h4, .stApp span { color: #332C28; }
    section[data-testid="stSidebar"] * { color: #332C28; }
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
    [class*="st-key-weekpick_"] button {
        border-radius: 50% !important; width: 2.5rem !important; min-width: 0 !important;
        height: 2.5rem !important; padding: 0 !important; margin: auto;
        border: 2px solid #A49C8C !important; background: transparent !important;
    }
    [class*="st-key-weekpick_"] button[kind="primary"] {
        background: #FF4B4B !important; border-color: #FF4B4B !important;
    }
    [class*="st-key-weekpick_"] button[kind="primary"] p { color: white !important; }
    [class*="st-key-weekday_"] button { border-radius: 6px !important; }
    [class*="st-key-weekday_"] button[kind="primary"] { background: #FCE4DA !important; border: 1px solid #E6B9AC !important; }
    [class*="st-key-periodpick_"] button[kind="secondary"] {background:#FAF9EE !important;border:1px solid #CECBC1 !important;}
    [class*="st-key-periodpick_"] button[kind="primary"] {background:#FCE4DA !important;border:1px solid #D97969 !important;}
    [class*="st-key-periodpick_"] button:disabled {opacity:.45;}
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

# 구글 캘린더 표준 이벤트 색상표 (Fallback용)
FALLBACK_EVENT_COLORS = {
    '1': '#7986cb', '2': '#33b679', '3': '#8e24aa', '4': '#e67c73',
    '5': '#f6c026', '6': '#f5511d', '7': '#039be5', '8': '#616161',
    '9': '#3f51b5', '10': '#0b8043', '11': '#d60000'
}

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
    
    # 검색 범위: 시작일 전날 ~ 종료일 다음날 (안전하게)
    search_start = datetime.combine(start_date, datetime.min.time()) - timedelta(days=1)
    search_end = datetime.combine(end_date, datetime.max.time()) + timedelta(days=1)
    time_min = search_start.isoformat() + 'Z'
    time_max = search_end.isoformat() + 'Z'

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

            items=[]; seen=set()
            chunk_start=search_start
            while chunk_start<search_end:
                chunk_end=min(search_end,datetime(chunk_start.year+1,1,1))
                token=None
                while True:
                    result=service.events().list(calendarId=cal_id,timeMin=chunk_start.isoformat()+'Z',timeMax=chunk_end.isoformat()+'Z',maxResults=2500,singleEvents=True,orderBy='startTime',pageToken=token).execute()
                    for item in result.get('items',[]):
                        identity=item.get('id')
                        if identity and identity in seen:continue
                        if identity:seen.add(identity)
                        items.append(item)
                    token=result.get('nextPageToken')
                    if not token:break
                chunk_start=chunk_end
            if items:
                for event in items:
                    event['calendar_id'] = cal_id
                    event['calendar_name'] = cal_name
                    
                    # 색상 결정 (V93 로직)
                    evt_color_id = event.get('colorId')
                    final_color = default_color
                    if evt_color_id:
                        if evt_color_id in event_colors_map:
                            final_color = event_colors_map[evt_color_id]['background']
                        elif evt_color_id in FALLBACK_EVENT_COLORS:
                            final_color = FALLBACK_EVENT_COLORS[evt_color_id]
                    event['real_color'] = final_color
                    all_events.append(event)
                log_msg.append(f"✅ [{cal_name}] : {len(items)}개")
            else:
                log_msg.append(f"⚠️ [{cal_name}] : 일정 없음")
                
        except Exception as e:
            log_msg.append(f"❌ [{cal_id}] 접근 불가: 로봇 공유 확인 필요")
            continue

    # [V95 핵심 로직] 날짜별 그룹핑 (Overnight 지원)
    daily_groups = {}
    curr = start_date
    while curr <= end_date:
        daily_groups[curr] = {'allday': [], 'timed': []}
        curr += timedelta(days=1)

    for event in all_events:
        start = event['start']
        # 1. 종일 일정 처리
        if 'date' in start:
            try:
                evt_date = datetime.strptime(start['date'], '%Y-%m-%d').date()
                end_date_str = event['end'].get('date')
                # 종일 일정은 종료일이 '다음날 0시'로 표기됨. 따라서 실제 종료일은 -1일
                evt_end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date() - timedelta(days=1)
                
                # 종일 일정도 여러 날에 걸칠 수 있음
                iter_date = evt_date
                while iter_date <= evt_end_date:
                    if start_date <= iter_date <= end_date:
                        daily_groups[iter_date]['allday'].append(event)
                    iter_date += timedelta(days=1)
            except: pass
            
        # 2. 시간 일정 처리 (수면 시간 등)
        elif 'dateTime' in start:
            try:
                # 시작/종료 시간 파싱 (KST 변환)
                dt_start = datetime.fromisoformat(start['dateTime'].replace('Z', '+00:00')).astimezone(KST)
                event['dt_object'] = dt_start # 원본 시작 시간 저장
                
                end_str = event['end'].get('dateTime')
                dt_end = datetime.fromisoformat(end_str.replace('Z', '+00:00')).astimezone(KST)
                event['dt_end_object'] = dt_end # 원본 종료 시간 저장

                # 이 이벤트가 '걸쳐있는' 모든 날짜를 찾아서 daily_groups에 넣기
                # 이벤트 시작일의 0시 0분
                curr_loop_dt = dt_start.date()
                end_loop_dt = dt_end.date()
                
                # 만약 종료 시간이 00:00:00 이라면, 날짜 상으로는 전날까지만 포함된 것으로 봄
                if dt_end.hour == 0 and dt_end.minute == 0 and dt_end.second == 0:
                    end_loop_dt -= timedelta(days=1)

                while curr_loop_dt <= end_loop_dt:
                    if start_date <= curr_loop_dt <= end_date:
                        # 해당 날짜에 이벤트 추가
                        # 주의: 객체를 그대로 넣으면 참조가 복사되므로, 렌더링 시 날짜별로 시간을 다르게 계산해야 함
                        daily_groups[curr_loop_dt]['timed'].append(event)
                    curr_loop_dt += timedelta(days=1)
                    
            except: pass
            
    for d in daily_groups:
        # 정렬: 그 날짜의 '표시될 시작 시간' 기준이 아니라, '원래 이벤트 시작 시간' 순서로 정렬
        daily_groups[d]['timed'].sort(key=lambda x: x['dt_object'])
            
    return daily_groups, cal_legend_info, log_msg

def calculate_visual_layout(events):
    if not events: return []
    # _s (시작 분) 기준으로 정렬
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
        # 클러스터 내에서 다시 정렬 (시작 시간 빠른 순, 길이는 긴 순)
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

def get_time_info(event, target_date):
    start_dt = event['dt_object']
    end_dt = event['dt_end_object']

    def format_endpoint(dt):
        offset = (dt.date() - target_date).days
        if offset == 0:
            return f"{dt:%H:%M}"
        if offset == -1:
            return f"전날 {dt:%H:%M}"
        if offset == 1:
            return f"익일 {dt:%H:%M}"
        return f"{dt:%m/%d %H:%M}" if dt.year == target_date.year else f"{dt:%Y/%m/%d %H:%M}"

    time_range = f"{format_endpoint(start_dt)} - {format_endpoint(end_dt)}"
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

def allday_span(e):
    try:
        a=date.fromisoformat(e['start']['date']); b=date.fromisoformat(e['end']['date'])-timedelta(days=1)
        return (a,b) if b>a else None
    except (KeyError, ValueError, TypeError): return None

def span_label(a,b):
    if a.year!=b.year: return f'{a:%Y/%m/%d}~{b:%Y/%m/%d}'
    return f'{a:%m/%d}~{b:%m/%d}'

def span_key(e):
    return (e.get('calendar_id'),e.get('id') or id(e))

DAILY_SIDEBAR_CSS = """
.daily-all { margin-top:15px; }
.daily-all-label { font-size:8pt; font-weight:bold; color:#666; margin-bottom:6px; }
.daily-all-row { font-size:8pt; line-height:1.35; margin-bottom:4px; padding-left:4px; border-left:2px solid; overflow-wrap:anywhere; word-break:break-all; }
.daily-all-period { font-size:7pt; color:#777; }
.daily-all-omitted { font-size:7pt; color:#777; border-top:1px solid #ddd; padding-top:3px; }
"""

def generate_day_html(target_date, data, cal_legend_info, ordered_ids, include_empty=False, planner=False):
    allday = data['allday']
    timed = data['timed']
    if not allday and not timed and not include_empty: return ""
    weekday_kr = ['월', '화', '수', '목', '금', '토', '일']
    date_str = f"{target_date.strftime('%Y-%m-%d')} ({weekday_kr[target_date.weekday()]})"
    
    from html import escape
    # Measure sidebar entries using the same font and physical width as the PDF.
    all_html = ""
    if allday:
        import re
        label = "종일 / 기간 일정" if planner else "종일 / 기간 일기"
        rows = []
        for evt in allday:
            span = allday_span(evt)
            period = f"{span_label(*span)} · {(target_date-span[0]).days+1}/{(span[1]-span[0]).days+1}일차" if span else ""
            color = str(evt.get('real_color', '#777'))
            if not re.fullmatch(r'#[0-9a-fA-F]{3}(?:[0-9a-fA-F]{3})?', color): color = '#777'
            rows.append(f"<div class='daily-all-row' style='border-color:{color};color:{color}'>{escape(str(evt.get('summary') or '(제목 없음)'))}" + (f"<div class='daily-all-period'>{escape(period)}</div>" if period else '') + '</div>')
        heading = f"<div class='daily-all-label'>{label}</div>"
        fc = FontConfiguration()
        def sidebar(n):
            extra = len(rows)-n
            return heading + ''.join(rows[:n]) + (f"<div class='daily-all-omitted'>생략 건수 {extra}건<br>상세 기록 참조</div>" if extra else '')
        def fits(n):
            doc = HTML(string='<meta charset="utf-8"><div class="measure">'+sidebar(n)+'</div>').render(stylesheets=[CSS(string='@page {size: 40.42mm 1000mm; margin:0} body {margin:0;font-family:NanumGothic,sans-serif;line-height:1.35} '+DAILY_SIDEBAR_CSS,font_config=fc)],font_config=fc)
            if len(doc.pages)!=1: return False
            box = next(x for x in doc.pages[0]._page_box.descendants() if getattr(x,'element_tag',None)=='div' and x.element.get('class')=='measure')
            return box.height <= 930
        lo, hi = 0, len(rows)
        while lo < hi:
            mid = (lo+hi+1)//2
            if fits(mid): lo=mid
            else: hi=mid-1
        all_html = "<div class='daily-all'>"+sidebar(lo)+"</div>"
    COL_HEIGHT = 950
    PIXELS_PER_MIN = COL_HEIGHT / 1440
    TOP_OFFSET = 10
    
    used_cal_ids = set()
    for evt in allday + timed: used_cal_ids.add(evt.get('calendar_id'))
    
    legend_html = "<div class='legend-container'>"
    for cal_id in ordered_ids:
        if cal_id in used_cal_ids:
            info = cal_legend_info.get(cal_id)
            if info: 
                legend_html += f"<div class='legend-row'><span class='legend-box' style='background-color:{info['color']}'></span><span class='legend-text'>{info['name']}</span></div>"
    legend_html += "</div>"

    visual_events = []
    
    # [V95] 타임라인 시각화 로직 수정 (Clamping)
    # 현재 그리는 날짜(target_date)의 00:00 ~ 24:00 기준
    day_start_dt = datetime.combine(target_date, datetime.min.time()).replace(tzinfo=KST)
    day_end_dt = day_start_dt + timedelta(days=1)

    for evt in timed:
        evt_start = evt['dt_object']
        evt_end = evt['dt_end_object']
        
        # 1. 시각화용 시작/종료 시간 계산 (Clamping)
        # 이벤트가 어제 시작했으면, 오늘 0시부터 시작한 것으로 간주
        vis_start = max(evt_start, day_start_dt)
        # 이벤트가 내일 끝나면, 오늘 24시까지만 그리기
        vis_end = min(evt_end, day_end_dt)
        
        # 만약 계산된 시작 >= 종료라면 (오류 방지), 그리지 않음
        if vis_start >= vis_end:
            continue

        # 분 단위 변환 (오늘 0시 기준)
        s_min = (vis_start - day_start_dt).total_seconds() / 60
        e_min = (vis_end - day_start_dt).total_seconds() / 60
        
        # 좌표 계산
        if e_min > 1440: e_min = 1440 # 안전장치
        
        real_color = evt.get('real_color', '#cccccc')
        item = {'summary': evt.get('summary',''), 'cal': evt.get('calendar_name',''), 'bg': real_color}
        
        visual_duration = max(e_min - s_min, 30) # 최소 높이 보장
        
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
            <div class='header-wrapper-full'>
                <div class='date-header'>{date_str}</div>
                {legend_html}
            </div>
            <div class='header-line-full'></div>
            
            <div class='content-wrapper'>
                <div class='text-column'> 
                    <div class='visual-page'>
                        <div class='timeline-col' style='top:10px;height:{COL_HEIGHT}px'>
    """
    
    for h in range(25):
        top = (h * 60 * PIXELS_PER_MIN) + TOP_OFFSET
        html += f"<div class='grid-line' style='top:{top}px;'></div>"
        
        label_top = top - 7
        if h == 24: label_top = top - 10
        
        span_style = "background-color:white; padding-right:2px;" 
        base_style = f"top:{label_top}px; left:0; width:30px; text-align:left; background-color:transparent; z-index:10;"
        
        if h % 3 == 0 or h == 24: 
             html += f"<div class='time-label' style='{base_style}'><span style='{span_style} color:#000; font-weight:bold;'>{h}</span></div>"
        else:
             html += f"<div class='time-label' style='{base_style}'><span style='{span_style} font-size:6pt; color:#666;'>{h}</span></div>"

    for item in timeline_items:
        GUTTER_PCT = 6.0
        w_pct = item['width'] * (100 - GUTTER_PCT) / 100
        l_pct = GUTTER_PCT + (item['left'] * (100 - GUTTER_PCT) / 100)
        
        top_px = (item['_s'] * PIXELS_PER_MIN) + TOP_OFFSET
        font_size = "7.5pt"
        line_height = '1.2'
        
        if item['_dur'] <= 30:
            wrap_style = "white-space: nowrap; overflow: hidden; text-overflow: ellipsis;"
        else:
            wrap_style = "white-space: normal; overflow: hidden;"
        
        html += f"<div class='event-block' style='top:{top_px}px; height:{item['_dur']*PIXELS_PER_MIN}px; left:{l_pct}%; width:{w_pct}%; background-color:{item['bg']}40; border-left:3px solid {item['bg']}; color:#333; font-size:{font_size}; line-height:{line_height}; z-index:20; {wrap_style}'><b>{item['summary']}</b></div>"
    
    html += f"""
                        </div>
                    </div> 
                </div> 
                <div class='memo-column'>{all_html}</div>
            </div>
        </div> 
    """
    
    text_items_flat = []
    for evt in allday: evt['is_allday'] = True; text_items_flat.append(evt)
    for evt in timed: evt['is_allday'] = False; text_items_flat.append(evt)
    
    if text_items_flat:
        html += f"""
        <div class='date-header-running'>{date_str} (계속)</div>
        <div class='content-wrapper text-pages-wrapper'>
            <div class='text-column'>
        """
        for evt in text_items_flat:
            raw_desc = evt.get('description','') or ''
            clean_desc = force_break_text(raw_desc).replace('\\n', '<br>')
            real_color = evt.get('real_color', '#333')
            if evt.get('is_allday'):
                span=allday_span(evt)
                period=f' ({span_label(*span)} · {(target_date-span[0]).days+1}/{(span[1]-span[0]).days+1}일차)' if span else ''
                title_html = f"<span class='text-title' style='color:{real_color};'>[종일] {evt.get('summary','')}{period}</span>"
                html += f"""<div class='text-item'><div class='allday-styled' style='border-color:{real_color};'>{title_html}<div class='text-desc'>{clean_desc}</div></div></div>"""
            else:
                t_range, dur_str = get_time_info(evt, target_date)
                meta_html = f"<span class='text-meta'><span style='color:{real_color}; font-weight:800; margin-right:5px;'>[{evt.get('calendar_name','')}]</span>{t_range} ({dur_str})</span>"
                title_html = f"<span class='text-title' style='color:{real_color};'>{evt.get('summary','')}</span>"
                html += f"""<div class='text-item'>{meta_html}{title_html}<div class='text-desc'>{clean_desc}</div></div>"""
        html += """</div></div>"""
    html += "</div>"
    return html

def create_full_pdf(daily_data, cal_legend_info, ordered_ids, side_margin_cm=2.4, column_gap_cm=0.85, entry_gap_px=17, include_empty=False, font_scale=1.0, planner=False):
    font_config = FontConfiguration()
    body_font = f"{8.5 * font_scale:g}pt"
    meta_font = f"{7.5 * font_scale:g}pt"
    title_font = f"{10 * font_scale:g}pt"
    
    css_style = f"""
        @page {{ size: A4; margin: 1.5cm; }}
        
        @page text_layer {{
            margin-top: 3.2cm;
            margin-left: {side_margin_cm:.2f}cm;
            margin-right: {side_margin_cm:.2f}cm; 
            @top-center {{
                content: element(headerContent);
                width: 17.5766667cm;
                vertical-align: top;
                padding-top: 1.7116667cm;
            }}
        }}
        
        body {{ font-family: 'NanumGothic', sans-serif; color: #333; line-height: 1.35; font-size: 8.5pt; }}
        
        .day-container {{ page-break-after: always; }}
        .first-page-container {{
            display: inline-block; width: 100%;
            page-break-inside: avoid; break-inside: avoid; margin-bottom: 20px;
        }}
        
        .header-wrapper-full {{ display: flex; justify-content: space-between; align-items: flex-end; margin-bottom: 5px; width: 100%; background-color: white;}}
        .header-line-full {{ width: 100%; height: 2px; background-color: #5d4037; margin-bottom: 10px; }}

        .date-header {{ font-size: 16pt; font-weight: bold; color: #3e2723; margin: 0; padding: 0; }}
        
        .legend-container {{ text-align: right; }}
        .legend-row {{ display: flex; align-items: center; justify-content: flex-end; margin-bottom: 2px; }}
        .legend-box {{ display: inline-block; width: 8px; height: 8px; margin-right: 5px; border-radius: 2px; border: 1px solid #ccc; }}
        .legend-text {{ font-size: 7pt; color: #666; }}
        
        .visual-page {{ width: 100%; height: 970px; position: relative; overflow: visible; margin-top: 5px; margin-bottom: 10px; }}
        .timeline-col {{ position: absolute; top: 10px; height: 950px; width: 100%; box-sizing: border-box; }}
        
        {DAILY_SIDEBAR_CSS}
        .grid-line {{ position: absolute; left: 0; width: 100%; height: 0; border-top: 1px dashed #bbb; z-index: 0; }}
        
        .time-label {{ position: absolute; left: 0; font-size: 7pt; font-weight: bold; color: #666; background-color: transparent; padding-right: 5px; z-index: 10; width: 30px; text-align: left; }}
        
        .event-block {{ position: absolute; border-radius: 6px; padding: 1px 3px; border: 1px solid white; box-shadow: 1px 1px 1px rgba(0,0,0,0.1); display: flex; flex-direction: column; justify-content: flex-start; z-index: 20; box-sizing: border-box; overflow: hidden; }}
        
        .date-header-running {{ 
            position: running(headerContent); 
            font-size: 16pt; font-weight: bold; color: #3e2723; 
            border-bottom: 2px solid #5d4037; 
            padding-bottom: 5px; margin: 0; 
            width: 100%; text-align: left;
        }}
        
        /* V96.2: 본문 2단에서 긴 엔트리의 본문이 다음 단으로 흐르도록 허용. 시간표 유지. */
        .text-pages-wrapper {{
            page: text_layer;
            display: block;
            width: 100%;
        }}
        .text-pages-wrapper > .text-column {{
            width: 100%;
            padding-right: 0;
            box-sizing: border-box;
            column-count: 2;
            column-gap: {column_gap_cm:.2f}cm;
            column-fill: auto;
        }}
        
        .content-wrapper {{ display: flex; width: 100%; }} 
        .text-column {{ width: 75%; padding-right: 2%; }} 
        .memo-column {{ width: 23%; }} 
        
        .text-item {{
            margin: 0 0 {entry_gap_px}px 0;
            padding: 0 0 8px 0;
            border-bottom: 1px solid #ece7e3;
            width: 100%;
            /* 엔트리 전체를 통째로 다음 단에 보내지 않는다. */
            break-inside: auto;
            page-break-inside: auto;
            orphans: 2;
            widows: 2;
        }}
        .allday-styled {{ background-color: #fff8e1; padding: 8px; border-radius: 6px; border-left: 3px solid; }}
        
        .text-meta {{ display: block; font-size: {meta_font}; color: #888; font-weight: bold; margin-bottom: 1px; break-after: avoid; page-break-after: avoid; }}
        .text-title {{ display: block; font-size: {title_font}; font-weight: bold; margin-bottom: 3px; break-after: avoid; page-break-after: avoid; }}
        
        .text-desc {{ 
            font-size: {body_font}; color: #444; white-space: pre-wrap; line-height: 1.5; word-break: break-all; overflow-wrap: break-word; 
            overflow-wrap: anywhere;
            /* 긴 설명은 단 경계에서 줄 단위로 나눌 수 있다. */
            break-inside: auto;
            orphans: 2;
            widows: 2;
        }}
    """
    
    full_html = "<html><body>"
    for d, events in sorted(daily_data.items()):
        full_html += generate_day_html(d, events, cal_legend_info, ordered_ids, include_empty, planner)
    full_html += "</body></html>"
    
    return HTML(string=full_html).write_pdf(stylesheets=[CSS(string=css_style, font_config=font_config)], font_config=font_config)


def week_start(d):
    return d - timedelta(days=(d.weekday()+1)%7)

def create_calendar_flow_pdf(daily_data, legend, ids, side_margin_cm, column_gap_cm, entry_gap_px, include_empty, font_scale, layout):
    from html import escape
    import calendar, re
    fc=FontConfiguration()
    monthly=layout.startswith('월간'); portrait='세로' in layout
    full='전체출력' in layout; adaptive='균등높이' not in layout
    footer='하단없음' not in layout
    width=((210 if portrait else 297)-20*side_margin_cm)/7
    budget=(297 if portrait else 210)-24-17
    base=(7.5 if portrait else 8)*font_scale
    gap=max(1,min(2,entry_gap_px/15))
    days=['일','월','화','수','목','금','토']
    def css(sz,g):
        return f'body{{margin:0;font-family:NanumGothic,sans-serif;font-size:{sz}pt;line-height:1.22}} .ev{{border-left:1.2pt solid;padding-left:.7mm;margin-bottom:{g}mm;overflow-wrap:anywhere;word-break:break-all;font-weight:bold}}'
    def event(e):
        c=str(e.get('real_color','#555555'))
        if not re.fullmatch(r'#[0-9a-fA-F]{3}(?:[0-9a-fA-F]{3})?',c): c='#555555'
        t=str(e.get('summary') or '(제목 없음)'); span=allday_span(e)
        if span: t+=' ('+span_label(*span)+')'
        return f'<div class="ev" style="color:{c};border-color:{c}">{escape(t)}</div>'
    def measure(items,sz,g):
        if not items:return []
        doc=HTML(string='<meta charset="utf-8">'+''.join(items)).render(stylesheets=[CSS(string=f'@page{{size:{width-2.6}mm 10000mm;margin:0}}'+css(sz,g),font_config=fc)],font_config=fc)
        return [(b.height+b.margin_top+b.margin_bottom)*25.4/96 for p in doc.pages for b in p._page_box.descendants() if type(b).__name__=='BlockBox' and b.element is not None and b.element.get('class')=='ev']
    def entries(row,month=None):
        result=[]
        for d in row:
            v=daily_data.get(d,{'allday':[],'timed':[]}) if month is None or d.month==month else {'allday':[],'timed':[]}
            result.append([event(e) for e in v['allday']+v['timed']])
        return result
    def chunks(items,sz,g,limit):
        hs=measure(items,sz,g); out=[]; cur=[]; used=0
        for item,h in zip(items,hs):
            if h>limit: raise ValueError('한 사건 제목이 페이지 높이를 초과합니다. 글자 크기를 줄여 주세요.')
            if cur and used+h>limit: out.append(cur); cur=[]; used=0
            cur.append(item); used+=h
        if cur:out.append(cur)
        return out or [[]]
    def row_html(row,cols,h,head=True,bottom=False,more=None,month=None,continued=None):
        labels=[(str(d.day) if month is not None else f'{d.month}/{d.day} ({days[i]})') if month is None or d.month==month else '' for i,d in enumerate(row)]
        heads='<tr>'+''.join('<th>'+x+'</th>' for x in labels)+'</tr>'
        cells=[]
        for i,items in enumerate(cols):
            marker='<div class="next">— 다음 페이지로 —</div>' if more and more[i] else ''
            prefix='<div class="prev">— 이어서 —</div>' if continued and continued[i] else ''
            cells.append(f'<td><div class="cell" style="height:{h}mm"><div>'+prefix+''.join(items)+'</div>'+marker+'</div></td>')
        return (heads if head else '')+'<tr>'+''.join(cells)+'</tr>'+(heads if bottom else '')
    def emit(out,title,body,sz,g):
        styles=f'@page{{size:A4 {"portrait" if portrait else "landscape"};margin:12mm {side_margin_cm}cm}} h1{{font-size:16pt;margin:0 0 3mm;border-bottom:1pt solid #63473c;padding-bottom:2mm}} table{{width:100%;table-layout:fixed;border-collapse:collapse}} th,td{{border:.6pt solid #bdb6ad;vertical-align:top;padding:0 1mm}} th{{height:5mm;background:#f1eee8;font-size:8pt;font-weight:normal}} .cell{{position:relative;padding-top:1mm;box-sizing:border-box}} .next{{position:absolute;bottom:1mm;left:0;right:0;border-top:1pt solid #444;font-size:6.5pt;font-weight:bold;text-align:center;color:#333}}.prev{{border-bottom:1pt solid #444;font-size:6.5pt;font-weight:bold;text-align:center;color:#333;margin-bottom:1mm}}'+css(sz,g)
        pdf=HTML(string='<meta charset="utf-8"><h1>'+escape(title)+'</h1><table>'+body+'</table>').write_pdf(stylesheets=[CSS(string=styles,font_config=fc)],font_config=fc)
        with fitz.open(stream=pdf,filetype='pdf') as doc:
            if len(doc)!=1:raise RuntimeError('달력 페이지 배치 초과')
            out.insert_pdf(doc)
    with fitz.open() as out:
        if not monthly:
            for w in sorted({week_start(d) for d in daily_data}):
                row=[w+timedelta(days=i) for i in range(7)]; es=entries(row); h=budget-16
                parts=[chunks(x,base,gap,h-15) for x in es]; n=max(map(len,parts))
                for j in range(n):
                    cols=[x[j] if j<len(x) else [] for x in parts]; more=[j+1<len(x) for x in parts]
                    title=f'{w:%Y.%m.%d} — {row[-1]:%Y.%m.%d}'+(f' ({j+1}/{n})' if n>1 else '')
                    emit(out,title,row_html(row,cols,h,j==0,footer,more,continued=[j>0 and j<len(x) for x in parts]),base,gap)
        else:
            first=min(daily_data).replace(day=1); rows=calendar.Calendar(firstweekday=6).monthdatescalendar(first.year,first.month); es=[entries(r,first.month) for r in rows]
            avail=budget-8; sz=base; g=gap
            def needs():return [max([sum(measure(x,sz,g)) for x in cols]+[0])+3 for cols in es]
            ns=needs()
            if not full:
                for sz,g in [(base,gap),(base,.6),(base*.95,.6),(base*.9,.6),(base*.85,.6)]:
                    ns=needs(); minimum=[max(12,n) for n in ns]
                    if (sum(minimum) if adaptive else max(minimum)*len(rows))+6*len(rows)<=avail:break
                else:
                    # Retain the established priority/omission engine as a last resort.
                    return create_weekly_pdf_legacy(daily_data,legend,ids,side_margin_cm,column_gap_cm,entry_gap_px,include_empty,font_scale,layout)
                hs=minimum if adaptive else [max(minimum)]*len(rows); extra=(avail-6*len(rows)-sum(hs))/len(rows); hs=[h+extra for h in hs]
                groups=[[(r,c,h) for r,c,h in zip(rows,es,hs)]]
            else:
                groups=[]; group=[]; used=0
                baseline=(avail-6*len(rows))/len(rows)
                if sum(max(12,n) for n in ns)+6*len(rows)<=avail:
                    # Same full-page allocation as compact mode, without shrinking text.
                    low=12 if adaptive else max(ns+[12])
                    hs=[max(low,n) for n in ns]
                    if sum(hs)+6*len(rows)<=avail:
                        extra=(avail-6*len(rows)-sum(hs))/len(rows)
                        groups=[[(r,c,h+extra,None,None) for r,c,h in zip(rows,es,hs)]]
                if not groups:
                    for r,c in zip(rows,es):
                        pending=[list(x) for x in c]; heights=[measure(x,sz,g) for x in c]; continued=[False]*7
                        while True:
                            room=avail-used-6
                            need=max([sum(x) for x in heights]+[0])+3+(6 if any(continued) else 0)
                            target=max(baseline,need)
                            if room>=target:
                                group.append((r,pending,target,None,continued));used+=target+6;break
                            # Start the next week in remaining space if useful, reserving markers.
                            if room<max(18,baseline*.35):
                                if group:groups.append(group);group=[];used=0;continue
                            limit=room-10-(6 if any(continued) else 0)
                            counts=[]
                            for hh in heights:
                                total=0;k=0
                                for v in hh:
                                    if total+v>limit:break
                                    total+=v;k+=1
                                counts.append(k)
                            if not any(counts):
                                if group:groups.append(group);group=[];used=0;continue
                                raise ValueError('한 사건 제목이 페이지 높이를 초과합니다. 글자 크기를 줄여 주세요.')
                            cols=[x[:k] for x,k in zip(pending,counts)]
                            pending=[x[k:] for x,k in zip(pending,counts)];heights=[x[k:] for x,k in zip(heights,counts)]
                            more=[bool(x) for x in pending]
                            group.append((r,cols,room,more,continued));groups.append(group);group=[];used=0
                            if not any(more):break
                            continued=more
                    if group:groups.append(group)
            for j,group in enumerate(groups):
                body='<tr>'+''.join('<th>'+d+'</th>' for d in days)+'</tr>'
                for item in group:
                    r,c,h=item[:3];more,continued=item[3:] if len(item)>3 else (None,None)
                    body+=row_html(r,c,h,month=first.month,more=more,continued=continued)
                emit(out,f'{first.year}년 {first.month}월'+(f' ({j+1}/{len(groups)})' if len(groups)>1 else ''),body,sz,g)
        return out.tobytes(garbage=3,deflate=True)

def create_weekly_pdf(*args):
    layout=args[-1]
    if layout.startswith('월간') or '전체출력' in layout:
        return create_calendar_flow_pdf(*args)
    return create_weekly_pdf_legacy(*args)

def create_weekly_pdf_legacy(daily_data, legend, ids, side_margin_cm, column_gap_cm, entry_gap_px, include_empty, font_scale, layout):
    from html import escape
    import re
    days = ['일','월','화','수','목','금','토']
    # Measure each column using the same renderer and font as the final PDF.
    fc = FontConfiguration()
    portrait = "세로" in layout
    width = ((210 if portrait else 297) - 20 * side_margin_cm) / 7
    monthly = layout.startswith("월간")
    height = 157
    def event_html(e, title):
        color = str(e.get('real_color', '#555555'))
        if not re.fullmatch(r'#[0-9a-fA-F]{3}(?:[0-9a-fA-F]{3})?', color): color = '#555555'
        return f'<div class="event" style="border-left-color:{color};color:{color}">{escape(title)}</div>'
    def style(size, gap):
        return f"""body {{margin:0;font-family:NanumGothic,sans-serif;font-size:{size}pt;line-height:1.22;color:#332c28;}} .event {{border-left:1.2pt solid;padding-left:.7mm;margin-bottom:{gap}mm;overflow-wrap:anywhere;word-break:break-all;font-weight:bold;}} .omission {{color:#777;font-size:6pt;line-height:1.1;margin-bottom:1mm;}} .omission-total {{color:#777;font-size:6.5pt;border-top:.4pt solid #bbb;padding-top:.6mm;margin-top:1mm;text-align:center;}}"""
    def fit_column(es, reserved=0):
        import unicodedata
        titles = [' '.join(str(e.get('summary') or '(제목 없음)').split()) for e in es]
        size = (7.5 if portrait else 8) * font_scale
        gap = max(1, min(2, entry_gap_px / 15))
        if not titles: return '', size, gap
        limit = (height - reserved - (7 if monthly else 3)) * 96 / 25.4
        def important(e):
            name = e.get('calendar_name') or legend.get(e.get('calendar_id'), {}).get('name', '')
            name = unicodedata.normalize('NFKC', str(name)).replace(' ', '')
            return '긍정' in name or '부정' in name or '올해의사건' in name
        def content(indices, ts):
            kept = set(indices); parts = []; missing = False
            for i in range(len(es)):
                if i not in kept:
                    missing = True
                    continue
                if missing:
                    parts.append('<div class="omission">···</div>'); missing = False
                parts.append(event_html(es[i], ts[i]))
            if len(indices) < len(es):
                parts.append(f'<div class="omission-total">생략 건수 {len(es)-len(indices)}건</div>')
            return ''.join(parts)
        def measure(html, sz, g):
            css = f'@page {{size:{width-2.5}mm 1000mm;margin:0;}}' + style(sz,g)
            doc = HTML(string='<meta charset="utf-8"><body><div class="measure">'+html+'</div></body>').render(stylesheets=[CSS(string=css,font_config=fc)],font_config=fc)
            if len(doc.pages)!=1: return float('inf')
            box = next(x for x in doc.pages[0]._page_box.descendants() if getattr(x,'element_tag',None)=='div' and x.element.get('class')=='measure')
            return box.height
        def two_lines(sz):
            # Measure all titles in a single render, then binary-search only overflowing titles.
            def counts(ts):
                html = ''.join(event_html(e,t) for e,t in zip(es,ts))
                css = f'@page {{size:{width-2.5}mm 10000mm;margin:0;}}' + style(sz,1)
                doc = HTML(string='<meta charset="utf-8"><body>'+html+'</body>').render(stylesheets=[CSS(string=css,font_config=fc)],font_config=fc)
                return [sum(type(y).__name__=='LineBox' for y in x.descendants()) for page in doc.pages for x in page._page_box.descendants() if type(x).__name__=='BlockBox' and getattr(x,'element_tag',None)=='div' and x.element.get('class')=='event']
            lo=[0]*len(titles); hi=[len(t) for t in titles]
            def cut(i,n): return titles[i] if n>=len(titles[i]) else titles[i][:n].rstrip()+'…'
            while any(a<b for a,b in zip(lo,hi)):
                mid=[(a+b+1)//2 for a,b in zip(lo,hi)]
                cs=counts([cut(i,n) for i,n in enumerate(mid)])
                if len(cs)!=len(titles): raise RuntimeError('주간 제목 줄 수 측정 실패')
                for i,n in enumerate(mid):
                    if lo[i]==hi[i]: continue
                    if cs[i]<=2: lo[i]=n
                    else: hi[i]=n-1
            return [cut(i,n) for i,n in enumerate(lo)]
        indices=list(range(len(es)))
        full=content(indices,titles)
        floor=max(min(size,6.5),size*.85)
        sizes=list(dict.fromkeys([size,max(floor,size*.95),max(floor,size*.90),floor]))
        for g in dict.fromkeys([gap,1,.6]):
            if measure(full,size,g)<=limit: return full,size,g
        gap=.6
        for sz in sizes[1:]:
            if measure(full,sz,gap)<=limit: return full,sz,gap
        sz=floor
        short=two_lines(sz)
        ts=[titles[i] if important(e) else short[i] for i,e in enumerate(es)]
        html=content(indices,ts)
        if measure(html,sz,gap)<=limit: return html,sz,gap
        for i in reversed(range(len(es))):
            if important(es[i]): continue
            indices.remove(i)
            html=content(indices,ts)
            if measure(html,sz,gap)<=limit: return html,sz,gap
        ts=short
        html=content(indices,ts)
        if measure(html,sz,gap)<=limit: return html,sz,gap
        for i in reversed(indices.copy()):
            indices.remove(i)
            html=content(indices,ts)
            if measure(html,sz,gap)<=limit: return html,sz,gap
        return content([],ts),sz,gap
    with fitz.open() as out:
        import calendar
        if monthly:
            first=min(daily_data).replace(day=1)
            weeks=calendar.Calendar(firstweekday=6).monthdatescalendar(first.year,first.month)
            split=layout.endswith('두 장')
            cut=(len(weeks)+1)//2
            groups=[weeks[:cut],weeks[cut:]] if split else [weeks]
            pages=[(f'{first.year}년 {first.month}월'+(f' ({i+1}/2)' if split else ''),g) for i,g in enumerate(groups)]
        else:
            pages=[(f'{w:%Y.%m.%d} — {w+timedelta(days=6):%Y.%m.%d}',[[w+timedelta(days=i) for i in range(7)]]) for w in sorted({week_start(d) for d in daily_data})]
        for title, rows in pages:
            height=((257 if portrait else 170) - 2.22*len(rows))/len(rows) if monthly else ((244 if portrait else 157)-(6 if "하단없음" not in layout else 0))/len(rows)
            body='<table>'
            if monthly: body+='<tr>'+''.join('<th>'+h+'</th>' for h in days)+'</tr>'
            for row in rows:
                heads=[]; cells=[]
                active_days=[d for d in row if d in daily_data and (not monthly or d.month==first.month)]
                spans={}
                for d in active_days:
                    for e in daily_data[d]['allday']:
                        if allday_span(e): spans[span_key(e)]=e
                lanes=[]; hidden=[]
                for e in sorted(spans.values(),key=lambda e:(allday_span(e)[0],allday_span(e)[1],str(e.get('summary','')))):
                    a,b=allday_span(e); covered=[i for i,d in enumerate(row) if d in active_days and a<=d<=b]
                    if not covered: continue
                    l,r=min(covered),max(covered)
                    lane=next((v for v in lanes if all(r<x or l>y for x,y,_ in v)),None)
                    if lane is None:
                        lane=[]; lanes.append(lane)
                    lane.append((l,r,e))
                # Preserve ordinary event space; report overflow instead of adding pages.
                max_lanes=max(1,min(6,int((height-(7 if monthly else 3))*.45/4.5)))
                if len(lanes)>max_lanes:
                    hidden=[e for lane in lanes[max_lanes:] for _,_,e in lane]; lanes=lanes[:max_lanes]
                reserved=len(lanes)*4.5+(4 if hidden else 0)
                for i,d in enumerate(row):
                    heads.append(f'{d.day}' if monthly and d in active_days else ('' if monthly else f'{d.month}/{d.day} ({days[i]})'))
                body+='<tr>'+''.join('<th class="dayhead">'+h+'</th>' for h in heads)+'</tr>'
                for lane in lanes:
                    body+='<tr class="spanrow">'; i=0
                    for l,r,e in sorted(lane):
                        while i<l: body+='<td class="spanblank"></td>'; i+=1
                        a,b=allday_span(e); color=str(e.get('real_color','#555555'))
                        if not re.fullmatch(r'#[0-9a-fA-F]{6}',color): color='#555555'
                        text=('← ' if a<row[l] else '')+str(e.get('summary') or '(제목 없음)')+' ('+span_label(a,b)+')'+(' →' if b>row[r] else '')
                        body+=f'<td class="spancell" colspan="{r-l+1}"><div class="spanbar" style="color:{color};border-color:{color}">{escape(text)}</div></td>'; i=r+1
                    while i<7: body+='<td class="spanblank"></td>'; i+=1
                    body+='</tr>'
                if hidden: body+=f'<tr><td colspan="7" class="spanhidden">종일 기간 일정 생략 {len(hidden)}건</td></tr>'
                for i,d in enumerate(row):
                    data=daily_data.get(d,{'allday':[],'timed':[]}); active=d in active_days
                    es=[e for e in data['allday'] if not allday_span(e)]+data['timed']
                    content,size,gap=fit_column(es,reserved+ (4 if monthly else 0)) if active else ('',8*font_scale,1)
                    cells.append(f'<td class="daybody" style="height:{max(1,height-reserved-(5 if monthly else 0))}mm;background:{"#fff" if active else "#f7f6f4"}"><div style="font-size:{size}pt;--gap:{gap}mm">{content}</div></td>')
                body+='<tr>'+''.join(cells)+'</tr>'
                if not monthly and '하단없음' not in layout: body+='<tr>'+''.join('<th class="dayhead">'+h+'</th>' for h in heads)+'</tr>'
            body+='</table>'
            css=f"""@page {{size:A4 {"portrait" if portrait else "landscape"};margin:{10 if monthly else 12}mm {side_margin_cm}cm;}} h1 {{font-size:16pt;border-bottom:1pt solid #63473c;padding-bottom:2mm;margin:0 0 3mm;}} table {{width:100%;table-layout:fixed;border-collapse:collapse;}} th,td {{border:.6pt solid #bdb6ad;vertical-align:top;padding:1mm;}} th {{background:#f1eee8;font-weight:normal;}} td {{height:{height}mm;}} .event {{margin-bottom:var(--gap);}}"""+style(8*font_scale,0)+'.event {margin-bottom:var(--gap);} .date-label {font-size:8pt;height:4mm;color:#555;} '
            css += '.dayhead{font-size:8pt;padding:.5mm 1mm;height:3mm}.spanrow td{height:4.5mm;padding:0 .5mm;border-top:0;border-bottom:0}.spanbar{box-sizing:border-box;height:4mm;line-height:3.5mm;font-size:7pt;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;border-left:1.5pt solid;background:#f1eee8;padding:0 1mm}.spanhidden{height:4mm;padding:0;font-size:6pt;color:#777;text-align:center}.daybody{border-top:0}'
            pdf=HTML(string='<meta charset="utf-8"><body><h1>'+title+'</h1>'+body+'</body>').write_pdf(stylesheets=[CSS(string=css,font_config=fc)],font_config=fc)
            with fitz.open(stream=pdf,filetype='pdf') as doc:
                if len(doc)!=1: raise RuntimeError('주간 양식을 한 페이지에 배치하지 못했습니다. 글자 크기 또는 여백을 줄여 주세요.')
                out.insert_pdf(doc)
        return out.tobytes(garbage=3,deflate=True)

def create_annual_pdf(daily_data, legend, ids, side_margin_cm, column_gap_cm, entry_gap_px, include_empty, font_scale, layout):
    from html import escape
    import re
    year=min(daily_data).year
    cols=2 if '두 열' in layout else 1
    split='두 장' in layout
    auto='자동' in layout
    fc=FontConfiguration()
    width=210-20*side_margin_cm
    cw=(width-19)/cols-3
    base=8*font_scale
    gap=max(1,min(2,entry_gap_px/15))
    months={m:[] for m in range(1,13)}
    for d,v in sorted(daily_data.items()):
        for e in v['allday']+v['timed']:
            # Annual highlights list each occurrence on its first visible day only.
            start=e.get('dt_object')
            origin=start.date() if start else date.fromisoformat(e.get('start',{}).get('date',str(d)))
            if d!=max(origin,date(year,1,1)): continue
            color=str(e.get('real_color','#555555'))
            if not re.fullmatch(r'#[0-9a-fA-F]{3}(?:[0-9a-fA-F]{3})?',color): color='#555555'
            name=str(e.get('calendar_name') or legend.get(e.get('calendar_id'),{}).get('name',''))
            span=allday_span(e)
            prefix=(f'{span[0].day:02d}~{span[1].day:02d}일' if span[0].year==span[1].year and span[0].month==span[1].month else span_label(*span)) if span else f'{d.day:02d}일'
            months[d.month].append((prefix+'  '+ ' '.join(str(e.get('summary') or '(제목 없음)').split()),color,'긍정' in name or '부정' in name))
    def css(sz,g):
        return f'body{{margin:0;font-family:NanumGothic,sans-serif;font-size:{sz}pt;line-height:1.22}} .ev{{border-left:1.2pt solid;padding-left:.7mm;margin-bottom:{g}mm;overflow-wrap:anywhere;word-break:break-all;font-weight:bold}} .omit{{font-size:6.5pt;color:#777;margin-bottom:1mm}}'
    def event(t,c): return f'<div class="ev" style="color:{c};border-color:{c}">{escape(t)}</div>'
    def measure(items,sz,g):
        if not items:return []
        doc=HTML(string='<meta charset="utf-8">'+''.join(items)).render(stylesheets=[CSS(string=f'@page{{size:{cw}mm 10000mm;margin:0}}'+css(sz,g),font_config=fc)],font_config=fc)
        return [(b.height+b.margin_top+b.margin_bottom)*25.4/96 for p in doc.pages for b in p._page_box.descendants() if type(b).__name__=='BlockBox' and b.element is not None and b.element.get('class') in ('ev','omit')]
    def partition(h):
        if cols==1:return len(h),sum(h)
        total=sum(h); acc=0; best=(total,0)
        for i in range(len(h)+1):
            best=min(best,(max(acc,total-acc),-i))
            if i<len(h):acc+=h[i]
        return -best[1],best[0]
    def prepare(es,sz,g,cap=False):
        ts=[e[0] for e in es]; items=[event(t,e[1]) for t,e in zip(ts,es)]; h=measure(items,sz,g)
        if cap:
            limit=2*sz*1.22*25.4/72+g+.05
            lo=[0]*len(ts); hi=[len(t) for t in ts]
            while any(a<b for a,b in zip(lo,hi)):
                mid=[(a+b+1)//2 for a,b in zip(lo,hi)]
                trial=[event(t if n==len(t) else t[:n].rstrip()+'…',e[1]) for t,n,e in zip(ts,mid,es)]
                hs=measure(trial,sz,g)
                for i,n in enumerate(mid):
                    if lo[i]==hi[i]:continue
                    if hs[i]<=limit:lo[i]=n
                    else:hi[i]=n-1
            items=[event(t if n==len(t) else t[:n].rstrip()+'…',e[1]) for t,n,e in zip(ts,lo,es)];h=measure(items,sz,g)
        return items,h
    def fit(es,limit):
        for sz,g,cap in [(base,gap,False),(base,1,False),(base,1,True),(max(min(base,6.5),base*.85),1,True)]:
            items,h=prepare(es,sz,g,cap)
            k,need=partition(h)
            if need<=limit:return items,k,sz,g
        keep=set(range(len(es))); order=[i for i in reversed(range(len(es))) if not es[i][2]]+[i for i in reversed(range(len(es))) if es[i][2]]
        for drop in order:
            keep.remove(drop); parts=[]; missing=False
            for i,item in enumerate(items):
                if i not in keep:missing=True;continue
                if missing:parts.append('<div class="omit">···</div>');missing=False
                parts.append(item)
            parts.append(f'<div class="omit">생략 건수 {len(es)-len(keep)}건</div>')
            k,need=partition(measure(parts,sz,g))
            if need<=limit:return parts,k,sz,g
        return [],0,sz,g
    with fitz.open() as out:
        for group in ([range(1,7),range(7,13)] if split else [range(1,13)]):
            group=list(group); total=257; minimum=12 if not split else 18
            needs=[partition(prepare(months[m],base,gap)[1])[1]+3 for m in group]
            if auto:
                extra=total-minimum*len(group); weights=[max(0,n-minimum)+minimum*.6 for n in needs]; s=sum(weights)
                heights=[minimum+extra*(w/s if s else 1/len(group)) for w in weights]
            else: heights=[total/len(group)]*len(group)
            body=''; title=f'{year}년'+(' 상반기' if group[0]==1 else ' 하반기') if split else f'{year}년'
            for m,h in zip(group,heights):
                items,k,sz,g=fit(months[m],h-3)
                parts=[items] if cols==1 else [items[:k],items[k:]]
                body+=f'<div class="month" style="height:{h}mm"><div class="label">{m}월</div>'+''.join(f'<div class="col" style="font-size:{sz}pt;--gap:{g}mm">'+''.join(p)+'</div>' for p in parts)+'</div>'
            styles=f'@page{{size:A4 portrait;margin:10mm {side_margin_cm}cm}} h1{{font-size:16pt;border-bottom:1pt solid #63473c;padding-bottom:2mm;margin:0 0 3mm}} .month{{display:flex;box-sizing:border-box;border:.5pt solid #bdb6ad;break-inside:avoid}} .label{{width:18mm;flex:none;background:#f1eee8;display:flex;align-items:center;justify-content:center;font-size:11pt;border-right:.5pt solid #bdb6ad}} .col{{width:{cw}mm;flex:none;padding:1mm;box-sizing:content-box}} .col+.col{{border-left:.4pt solid #ddd}}'+css(base,gap)+'.ev{margin-bottom:var(--gap)}'
            pdf=HTML(string='<meta charset="utf-8"><h1>'+title+'</h1>'+body).write_pdf(stylesheets=[CSS(string=styles,font_config=fc)],font_config=fc)
            with fitz.open(stream=pdf,filetype='pdf') as doc:
                if len(doc)!=1:raise RuntimeError('연간 페이지 배치 실패')
                out.insert_pdf(doc)
        return out.tobytes(garbage=3,deflate=True)

def create_multiyear_pdf(daily_data, legend, ids, side_margin_cm, column_gap_cm, entry_gap_px, include_empty, font_scale, layout):
    from html import escape
    import re
    first=min(daily_data).year
    last=max(daily_data).year
    cols=2 if '두 열' in layout else 1
    split='두 장' in layout
    auto='자동 배분' in layout
    fc=FontConfiguration()
    width=210-20*side_margin_cm
    cw=(width-23)/cols-3
    base=8*font_scale
    gap=max(1,min(2,entry_gap_px/15))
    months={y:[] for y in range(first,last+1)}
    for d,v in sorted(daily_data.items()):
        for e in v['allday']+v['timed']:
            # Annual highlights list each occurrence on its first visible day only.
            start=e.get('dt_object')
            origin=start.date() if start else date.fromisoformat(e.get('start',{}).get('date',str(d)))
            if d!=max(origin,min(daily_data)): continue
            color=str(e.get('real_color','#555555'))
            if not re.fullmatch(r'#[0-9a-fA-F]{3}(?:[0-9a-fA-F]{3})?',color): color='#555555'
            name=str(e.get('calendar_name') or legend.get(e.get('calendar_id'),{}).get('name',''))
            span=allday_span(e)
            prefix=span_label(*span) if span else f'{d:%m.%d}'
            months[d.year].append((prefix+'  '+ ' '.join(str(e.get('summary') or '(제목 없음)').split()),color,'긍정' in name or '부정' in name or '올해의 사건' in name))
    def css(sz,g):
        return f'body{{margin:0;font-family:NanumGothic,sans-serif;font-size:{sz}pt;line-height:1.22}} .ev{{border-left:1.2pt solid;padding-left:.7mm;margin-bottom:{g}mm;overflow-wrap:anywhere;word-break:break-all;font-weight:bold}} .omit{{font-size:6.5pt;color:#777;margin-bottom:1mm}}'
    def event(t,c): return f'<div class="ev" style="color:{c};border-color:{c}">{escape(t)}</div>'
    def measure(items,sz,g):
        if not items:return []
        doc=HTML(string='<meta charset="utf-8">'+''.join(items)).render(stylesheets=[CSS(string=f'@page{{size:{cw}mm 10000mm;margin:0}}'+css(sz,g),font_config=fc)],font_config=fc)
        return [(b.height+b.margin_top+b.margin_bottom)*25.4/96 for p in doc.pages for b in p._page_box.descendants() if type(b).__name__=='BlockBox' and b.element is not None and b.element.get('class') in ('ev','omit')]
    def partition(h):
        if cols==1:return len(h),sum(h)
        total=sum(h); acc=0; best=(total,0)
        for i in range(len(h)+1):
            best=min(best,(max(acc,total-acc),-i))
            if i<len(h):acc+=h[i]
        return -best[1],best[0]
    def prepare(es,sz,g,cap=False):
        ts=[e[0] for e in es]; items=[event(t,e[1]) for t,e in zip(ts,es)]; h=measure(items,sz,g)
        if cap:
            limit=2*sz*1.22*25.4/72+g+.05
            lo=[0]*len(ts); hi=[len(t) for t in ts]
            while any(a<b for a,b in zip(lo,hi)):
                mid=[(a+b+1)//2 for a,b in zip(lo,hi)]
                trial=[event(t if n==len(t) else t[:n].rstrip()+'…',e[1]) for t,n,e in zip(ts,mid,es)]
                hs=measure(trial,sz,g)
                for i,n in enumerate(mid):
                    if lo[i]==hi[i]:continue
                    if hs[i]<=limit:lo[i]=n
                    else:hi[i]=n-1
            items=[event(t if n==len(t) else t[:n].rstrip()+'…',e[1]) for t,n,e in zip(ts,lo,es)];h=measure(items,sz,g)
        return items,h
    def fit(es,limit):
        for sz,g,cap in [(base,gap,False),(base,1,False),(base,1,True),(max(min(base,6.5),base*.85),1,True)]:
            items,h=prepare(es,sz,g,cap)
            k,need=partition(h)
            if need<=limit:return items,k,sz,g
        keep=set(range(len(es))); order=[i for i in reversed(range(len(es))) if not es[i][2]]+[i for i in reversed(range(len(es))) if es[i][2]]
        for drop in order:
            keep.remove(drop); parts=[]; missing=False
            for i,item in enumerate(items):
                if i not in keep:missing=True;continue
                if missing:parts.append('<div class="omit">···</div>');missing=False
                parts.append(item)
            parts.append(f'<div class="omit">생략 건수 {len(es)-len(keep)}건</div>')
            k,need=partition(measure(parts,sz,g))
            if need<=limit:return parts,k,sz,g
        return [f'<div class="omit">생략 건수 {len(es)}건</div>'] if es else [],0 if cols==2 else 1,sz,g
    years=list(months)
    total=257
    needs={y:partition(prepare(months[y],base,gap)[1])[1]+3 for y in years}
    if '자동 페이지' in layout:
        groups=[]; group=[]; used=0
        for y in years:
            need=max(12,needs[y])
            if need>total:
                raise ValueError(f'{y}년 기록이 한 페이지를 초과합니다. 캘린더를 줄이거나 글자 크기를 작게 선택하세요.')
            if group and (used+need>total or (not auto and max([need]+[max(12,needs[z]) for z in group])*(len(group)+1)>total)):
                groups.append(group);group=[];used=0
            group.append(y);used+=need
        if group:groups.append(group)
    elif split and len(years)>1:
        mid=(len(years)+1)//2;groups=[years[:mid],years[mid:]]
    else:groups=[years]
    with fitz.open() as out:
        for group in groups:
            if len(group)*8>total:
                raise ValueError('연도 수가 너무 많습니다. 자동 페이지를 선택하세요.')
            minimum=min(12,total/len(group))
            if auto:
                weights=[max(0,needs[y]-minimum) for y in group]
                extra=total-minimum*len(group); weight=sum(weights)
                heights=[minimum+extra*(w/weight if weight else 1/len(group)) for w in weights]
            else:heights=[total/len(group)]*len(group)
            if '자동 페이지' in layout:
                required=[max(12,needs[y]) for y in group]
                if not auto and max(required)*len(group)>total:
                    raise ValueError('균등 배치로 모든 사건을 담을 수 없습니다. 자동 높이 배분을 선택하세요.')
                if auto:heights=[n+(total-sum(required))/len(group) for n in required]
            body=''; title=f'{group[0]} — {group[-1]}' if len(group)>1 else f'{group[0]}년'
            for m,h in zip(group,heights):
                items,k,sz,g=fit(months[m],h-3)
                parts=[items] if cols==1 else [items[:k],items[k:]]
                body+=f'<div class="month" style="height:{h}mm"><div class="label">{m}년</div>'+''.join(f'<div class="col" style="font-size:{sz}pt;--gap:{g}mm">'+''.join(p)+'</div>' for p in parts)+'</div>'
            styles=f'@page{{size:A4 portrait;margin:10mm {side_margin_cm}cm}} h1{{font-size:16pt;border-bottom:1pt solid #63473c;padding-bottom:2mm;margin:0 0 3mm}} .month{{display:flex;box-sizing:border-box;border:.5pt solid #bdb6ad;break-inside:avoid}} .label{{width:22mm;flex:none;background:#f1eee8;display:flex;align-items:center;justify-content:center;font-size:11pt;border-right:.5pt solid #bdb6ad}} .col{{width:{cw}mm;flex:none;padding:1mm;box-sizing:content-box}} .col+.col{{border-left:.4pt solid #ddd}}'+css(base,gap)+'.ev{margin-bottom:var(--gap)}'
            pdf=HTML(string='<meta charset="utf-8"><h1>'+title+'</h1>'+body).write_pdf(stylesheets=[CSS(string=styles,font_config=fc)],font_config=fc)
            with fitz.open(stream=pdf,filetype='pdf') as doc:
                if len(doc)!=1:raise RuntimeError('다년간 페이지 배치 실패')
                out.insert_pdf(doc)
        return out.tobytes(garbage=3,deflate=True)

def period_end(d, kind):
    import calendar
    if kind == '월간': return date(d.year,d.month,calendar.monthrange(d.year,d.month)[1])
    if kind == '연간': return date(d.year,12,31)
    return d+timedelta(days=6)

def period_start(d, kind):
    if kind == '월간': return d.replace(day=1)
    if kind == '연간': return d.replace(month=1,day=1)
    return week_start(d)

def render_period_picker(kind, mode, today, planner):
    prefix='v985_'+kind+mode
    sk=prefix+'_selected'; nk=prefix+'_nav'
    current=period_start(today,kind)
    if sk not in st.session_state: st.session_state[sk]={current}
    if nk not in st.session_state: st.session_state[nk]=today.year if kind=='월간' else today.year//10*10
    def allowed(d):
        return 1900<=d.year<=2100 and (period_end(d,kind)>=today if planner else d<=today)
    def toggle(d):
        chosen=set(st.session_state[sk]); chosen.symmetric_difference_update({d}); st.session_state[sk]=chosen
    def move(delta): st.session_state[nk]+=delta
    def select_all(ds): st.session_state[sk]=set(st.session_state[sk])|set(ds)
    n=st.session_state[nk]; step=1 if kind=='월간' else 10
    lo=(today.year if planner else 1900) if kind=='월간' else (today.year//10*10 if planner else 1900)
    hi=(2100 if planner else today.year) if kind=='월간' else (2100 if planner else today.year//10*10)
    a,b,c=st.columns([1,4,1]); a.button('◀',key=prefix+'prev',on_click=move,args=(-step,),disabled=n<=lo,use_container_width=True)
    b.markdown(f'<div style="text-align:center;font-size:1.25rem;font-weight:bold">{n}년</div>' if kind=='월간' else f'<div style="text-align:center;font-size:1.25rem;font-weight:bold">{n} — {n+9}</div>',unsafe_allow_html=True)
    c.button('▶',key=prefix+'next',on_click=move,args=(step,),disabled=n>=hi,use_container_width=True)
    ds=[date(n,m,1) for m in range(1,13)] if kind=='월간' else [date(y,1,1) for y in range(n,n+10)]
    width=3 if kind=='월간' else 2
    for i in range(0,len(ds),width):
        for col,d in zip(st.columns(width),ds[i:i+width]):
            checked=d in st.session_state[sk]
            label=('✓  ' if checked else '○  ')+(f'{d.month}월' if kind=='월간' else f'{d.year}년')
            col.button(label,key="periodpick_"+prefix+str(d),type='primary' if checked else 'secondary',disabled=not allowed(d),on_click=toggle,args=(d,),use_container_width=True)
    a,b,c=st.columns(3)
    a.button('전체 선택',key=prefix+'all',on_click=select_all,args=([d for d in ds if allowed(d)],))
    b.button('올해',key=prefix+'today',on_click=lambda:st.session_state.update({nk:today.year if kind=='월간' else today.year//10*10}))
    c.button('선택 해제',key=prefix+'clear',on_click=lambda:st.session_state.update({sk:set()}))
    chosen=tuple(sorted(d for d in st.session_state[sk] if allowed(d)))
    for d in chosen:
        a,b=st.columns([5,1]); a.write(f'{d.year}년 {d.month}월' if kind=='월간' else f'{d.year}년'); b.button('×',key=prefix+'remove'+str(d),on_click=toggle,args=(d,))
    return chosen

def render_body(*args, planner=False):
    *base, layout = args
    if layout.startswith(('월간','연간')):
        kind=layout.split()[0]
        data,*settings=base
        groups={}
        for d,v in sorted(data.items()): groups.setdefault(period_start(d,kind),{})[d]=v
        engine=create_annual_pdf if kind=='연간' else create_weekly_pdf
        with fitz.open() as out:
            for group in groups.values():
                with fitz.open(stream=engine(group,*settings,layout),filetype='pdf') as doc: out.insert_pdf(doc)
            return out.tobytes(garbage=3,deflate=True)
    return create_full_pdf(*base, planner=planner) if layout=='일간' else create_multiyear_pdf(*base,layout) if layout.startswith('다년간') else create_annual_pdf(*base,layout) if layout.startswith('연간') else create_weekly_pdf(*base,layout)

# --- [6. Main UI] ---
# Google Calendar is fetched once; print-layout changes reuse the downloaded events.
for key, default in {
    "pdf_data": None, "cached_diary": None, "preview_pdf": None,
    "preview_key": None, "preview_page": 1, "full_pdf_key": None,
}.items():
    if key not in st.session_state:
        st.session_state[key] = default

st.title("📝 시온이네 일기장 인쇄소")
today = datetime.now(KST).date()
if "v98_mode" not in st.session_state:
    st.session_state["v98_mode"] = None

def choose_mode(mode):
    if st.session_state["v98_mode"] != mode:
        for key in ("pdf_data", "cached_diary", "preview_pdf", "preview_key", "full_pdf_key"):
            st.session_state[key] = None
        st.session_state["preview_page"] = 1
        st.session_state["v98_mode"] = mode

left, right = st.columns(2)
with left:
    st.button("📖 일기", use_container_width=True, on_click=choose_mode, args=("일기",))
    st.caption("지나온 시간의 기록과 보존")
with right:
    st.button("📅 플래너", use_container_width=True, on_click=choose_mode, args=("플래너",))
    st.caption("다가올 시간의 계획과 준비")
mode = st.session_state["v98_mode"]
if mode is None:
    st.info("일기 또는 플래너를 선택하세요.")
    st.stop()
planner = mode == "플래너"
st.header(mode + " · 인쇄")
layout = st.radio("인쇄 양식", ["일간", "주간", "월간", "연간", "다년간"], horizontal=True, key="v9812_layout_"+mode)
service, robot_email = get_calendar_service()

body_ready = False
body_args = None
body_key = None
if service:
    with st.sidebar:
        st.header("⚙️ 설정")
        st.info("🤖 **이 로봇을 캘린더에 초대하세요:**")
        st.code(robot_email, language="text")
        st.divider()
        st.markdown("**👇 캘린더 ID 입력** (콤마로 구분, `| 색상` 옵션)")
        default_ids = st.secrets.get("default_calendar_ids", "")
        if not isinstance(default_ids, str):
            st.error("Secrets의 default_calendar_ids는 문자열로 설정해주세요.")
            default_ids = ""
        manual = st.text_area("ID 목록", value=default_ids, height=120)
        if default_ids:
            st.caption("✅ 저장된 캘린더 목록을 불러왔습니다.")
        else:
            st.caption("💡 Streamlit Settings → Secrets에 default_calendar_ids를 저장할 수 있습니다.")

    # Resolve configured calendars and calendars visible to the service account.
    configured, custom_colors = {}, {}
    for item in manual.split(','):
        cid, sep, color = item.strip().partition('|'); cid=cid.strip()
        if cid:
            configured[cid]=cid
            if sep: custom_colors[cid]=normalize_color(color.strip())
    catalog_key='v982_catalog_'+manual
    if catalog_key not in st.session_state:
        catalog=dict(configured)
        try:
            token=None
            while True:
                result=service.calendarList().list(pageToken=token).execute()
                for c in result.get('items',[]):
                    catalog[c['id']]=c.get('summaryOverride') or c.get('summary') or c['id']
                    if c['id'] not in custom_colors and c.get('backgroundColor'): custom_colors[c['id']]=c['backgroundColor']
                token=result.get('nextPageToken')
                if not token: break
        except Exception: pass
        for cid in configured:
            try: catalog[cid]=service.calendars().get(calendarId=cid).execute().get('summary',cid)
            except Exception: pass
        st.session_state[catalog_key]=(catalog,custom_colors)
    catalog,custom_colors=st.session_state[catalog_key]
    def default_selected(name):
        if planner or layout not in ('월간','연간','다년간'): return True
        if layout in ('연간','다년간') and any('올해의 사건' in n for n in catalog.values()): return '올해의 사건' in name
        return '긍정' in name or '부정' in name or '올해의사건' in name or not any('긍정' in n or '부정' in n for n in catalog.values())
    with st.sidebar:
        st.subheader('인쇄할 캘린더')
        if st.button('캘린더 목록 새로고침'):
            del st.session_state[catalog_key]; st.rerun()
        final_ids=[cid for cid,name in catalog.items() if st.checkbox(name,value=default_selected(name),key='v982_cal_'+mode+layout+cid)]
        st.caption('현재는 서비스 계정에 공유된 캘린더만 표시됩니다. 누락된 캘린더는 ID를 추가하세요.')
    selected_weeks = None
    if layout=='일간':
        col1,col2=st.columns(2)
        with col1:
            start_d=st.date_input('시작 날짜',today,min_value=today if planner else date(1900,1,1),max_value=date(2100,12,31) if planner else today,key='v98_start_'+mode)
        with col2:
            end_d=st.date_input('종료 날짜',today,min_value=today if planner else date(1900,1,1),max_value=date(2100,12,31) if planner else today,key='v98_end_'+mode)
        include_empty=st.checkbox('일정이 없는 날짜도 인쇄',value=planner,key='v98_empty_'+mode)
    elif layout in ('월간','연간'):
        kind=layout
        selected_weeks=render_period_picker(kind,mode,today,planner)
        start_d=selected_weeks[0] if selected_weeks else today
        end_d=period_end(selected_weeks[-1],kind) if selected_weeks else today
        include_empty=True
        if kind=='월간':
            layout='월간 한 장'
            st.caption(f'선택한 {len(selected_weeks)}개월')
        else:
            pages=st.radio('페이지 구성',['한 장','두 장'],horizontal=True,key='annual_pages_'+mode)
            columns=st.radio('사건 배치',['한 열','두 열'],index=1,horizontal=True,key='annual_cols_'+mode)
            heights=st.radio('월별 높이',['자동 배분','균등 배치'],horizontal=True,key='annual_height_'+mode)
            layout='연간 '+pages+' '+columns+' '+heights
            st.caption(f'선택한 {len(selected_weeks)}년 · A4 {len(selected_weeks)*(2 if pages=="두 장" else 1)}장')
    elif layout=='다년간':
        low,high=(today.year,2100) if planner else (1900,today.year)
        c1,c2=st.columns(2)
        with c1: first=st.selectbox('시작 연도',list(range(low,high+1)),index=max(0,today.year-9-low) if not planner else 0,key='multi_first_'+mode)
        with c2: last=st.selectbox('종료 연도',list(range(first,high+1)),index=min(high-first,9) if planner else high-first,key='multi_last_'+mode)
        start_d=date(first,1,1);end_d=date(last,12,31);include_empty=True
        pages=st.radio('페이지 구성',['한 장','두 장','자동 페이지'],horizontal=True,key='multi_pages_'+mode)
        columns=st.radio('사건 배치',['한 열','두 열'],index=1,horizontal=True,key='multi_cols_'+mode)
        heights=st.radio('연도별 높이',['자동 배분','균등 배치'],horizontal=True,key='multi_height_'+mode)
        layout='다년간 '+pages+' '+columns+' '+heights
        st.caption(f'총 {last-first+1}년 · 주요 사건 캘린더를 권장합니다.')
    else:
        import calendar
        prefix_week = 'v9842_'+mode+'_'
        selection_key = prefix_week+'selected'
        month_key = prefix_week+'month'
        if selection_key not in st.session_state:
            st.session_state[selection_key] = {week_start(today)}
        if month_key not in st.session_state:
            st.session_state[month_key] = today.replace(day=1)
        def allowed_week(w):
            return date(1900,1,1) <= w+timedelta(days=6) and w <= date(2100,12,31) and (w+timedelta(days=6)>=today if planner else w<=today)
        def move_month(delta):
            m=st.session_state[month_key]
            n=m.year*12+m.month-1+delta
            st.session_state[month_key]=date(n//12,n%12+1,1)
        def toggle_week(w):
            chosen=set(st.session_state[selection_key])
            if w in chosen: chosen.remove(w)
            elif allowed_week(w): chosen.add(w)
            st.session_state[selection_key]=chosen
        def select_month(ws):
            st.session_state[selection_key]=set(st.session_state[selection_key]) | set(ws)
        m=st.session_state[month_key]
        lo=today.replace(day=1) if planner else date(1900,1,1)
        hi=date(2100,12,1) if planner else today.replace(day=1)
        if not lo<=m<=hi:
            m=today.replace(day=1); st.session_state[month_key]=m
        st.caption('인쇄할 주의 왼쪽 원 또는 날짜 행을 선택하세요. 여러 달의 선택도 유지됩니다.')
        c1,c2,c3=st.columns([1,4,1])
        c1.button('◀',key=prefix_week+'prev',on_click=move_month,args=(-1,),disabled=m<=lo,use_container_width=True)
        c2.markdown(f'<div style="text-align:center;font-size:1.25rem;font-weight:bold">{m.year}년 {m.month}월</div>',unsafe_allow_html=True)
        c3.button('▶',key=prefix_week+'next',on_click=move_month,args=(1,),disabled=m>=hi,use_container_width=True)
        rows=calendar.Calendar(firstweekday=6).monthdatescalendar(m.year,m.month)
        header=st.columns(8)
        for c,label in zip(header,['선택','일','월','화','수','목','금','토']):
            c.markdown(f'<div style="text-align:center">{label}</div>',unsafe_allow_html=True)
        for row in rows:
            w=row[0]; checked=w in st.session_state[selection_key]; valid=allowed_week(w)
            cells=st.columns(8)
            for i,c in enumerate(cells):
                label=('✓' if checked else '○') if i==0 else str(row[i-1].day)
                c.button(label,key=('weekpick_' if i==0 else 'weekday_')+prefix_week+str(w)+'_'+str(i),disabled=not valid,on_click=toggle_week,args=(w,),type='primary' if checked else 'secondary',use_container_width=True,help=f'{w:%Y.%m.%d} ~ {row[-1]:%Y.%m.%d}')
        a,b,c=st.columns(3)
        a.button('이달 전체 선택',key=prefix_week+'all',on_click=select_month,args=([r[0] for r in rows if allowed_week(r[0])],))
        b.button('이번 달',key=prefix_week+'today',on_click=lambda: st.session_state.update({month_key:today.replace(day=1)}))
        c.button('선택 해제',key=prefix_week+'clear',on_click=lambda: st.session_state.update({selection_key:set()}))
        selected_weeks=tuple(sorted(w for w in st.session_state[selection_key] if allowed_week(w)))
        st.caption(f'선택한 {len(selected_weeks)}주')
        for w in selected_weeks:
            label,remove=st.columns([5,1])
            label.write(f'{w:%Y.%m.%d} ~ {w+timedelta(days=6):%Y.%m.%d}')
            remove.button('×',key=prefix_week+'remove_'+str(w),on_click=toggle_week,args=(w,))
        start_d=selected_weeks[0] if selected_weeks else today
        end_d=selected_weeks[-1]+timedelta(days=6) if selected_weeks else today
        include_empty=True

    if layout.startswith(('주간','월간')):
        direction=st.radio('용지 방향',['가로','세로'],horizontal=True,key='paper_direction_'+mode+layout.split()[0])
        layout += ' '+direction
        kind=layout.split()[0]
        output=st.radio('출력 방식',['모든 기록 출력','한 페이지에 맞추기'] if kind=='주간' else ['한 페이지에 맞추기','모든 기록 출력'],key='flow_'+mode+kind)
        layout += ' 전체출력' if output=='모든 기록 출력' else ' 한장맞춤'
        if kind=='월간':
            layout += ' 균등높이' if st.radio('주별 높이',['자동 배분','균등 배치'],horizontal=True,key='height_'+mode)=='균등 배치' else ' 자동높이'
        else:
            if not st.checkbox('하단 날짜·요일 표시',value=True,key='footer_'+mode):layout+=' 하단없음'

    if layout == '일간' and (end_d - start_d).days > 100:
        st.warning("⚠️ 기간이 100일을 넘으면 서버 메모리 부족이 발생할 수 있습니다.")

    if st.button(f"📅 캘린더 {mode} 불러오기", type="primary", disabled=selected_weeks == ()):
        for key in ("pdf_data", "cached_diary", "preview_pdf", "preview_key", "full_pdf_key"):
            st.session_state[key] = None
        if not final_ids:
            st.error("캘린더 ID를 입력해주세요!")
        elif start_d > end_d:
            st.error("날짜 선택이 잘못되었습니다.")
        else:
            with st.spinner("캘린더에서 일기를 불러오는 중입니다..."):
                if selected_weeks is None:
                    daily_data, cal_legend_info, logs = get_events_from_ids(service, final_ids, custom_colors, start_d, end_d)
                else:
                    daily_data, cal_legend_info, logs = {}, {}, []
                    groups=[]
                    for w in selected_weeks:
                        finish=period_end(w,layout.split()[0])
                        if groups and w == groups[-1][1]+timedelta(days=1):
                            groups[-1]=(groups[-1][0],finish)
                        else: groups.append((w,finish))
                    for a,b in groups:
                        data, legend, messages=get_events_from_ids(service,final_ids,custom_colors,a,b)
                        daily_data.update(data); cal_legend_info.update(legend); logs.extend(messages)
            total_count = sum(len(v["allday"]) + len(v["timed"]) for v in daily_data.values())
            with st.expander("🔎 처리 결과 로그"):
                for log in logs:
                    if "❌" in log: st.error(log)
                    elif "⚠️" in log: st.warning(log)
                    else: st.success(log)
            if any("❌" in log for log in logs):
                st.error("일부 캘린더를 조회하지 못했습니다. 공유 설정을 확인하고 다시 불러오세요.")
            elif total_count == 0 and not include_empty:
                st.warning("가져온 기록이 없습니다. 빈 날짜 인쇄를 선택할 수 있습니다.")
            else:
                st.session_state["cached_diary"] = {
                    "data": daily_data, "legend": cal_legend_info,
                    "ids": final_ids, "start": start_d, "end": end_d,
                    "count": total_count, "manual": manual, "weeks": selected_weeks, "kind": layout.split()[0],
                }
                st.session_state["preview_key"] = None
                st.session_state["preview_pdf"] = None
                st.session_state["preview_page"] = 1
                st.session_state["pdf_data"] = None
                st.session_state["full_pdf_key"] = None
                st.success(f"총 {total_count}개 기록을 불러왔습니다. 이제 여백을 조절해 보세요.")

    cached = st.session_state["cached_diary"]
    if cached and (cached["start"] != start_d or cached["end"] != end_d or cached["ids"] != final_ids or cached.get("manual") != manual or cached.get("weeks") != selected_weeks or cached.get("kind") != layout.split()[0]):
        st.info("날짜 또는 캘린더 선택이 변경되었습니다. 다시 불러오세요.")
    if cached and cached["start"] == start_d and cached["end"] == end_d and cached["ids"] == final_ids and cached.get("manual") == manual and cached.get("weeks") == selected_weeks and cached.get("kind") == layout.split()[0] and selected_weeks != ():
        if cached["start"] != start_d or cached["end"] != end_d:
            st.warning("선택한 날짜가 불러온 일기의 기간과 다릅니다. 새 기간을 적용하려면 다시 불러오세요.")
        st.subheader("인쇄 설정")
        st.caption("선택한 하루 또는 한 주의 실제 PDF를 미리 봅니다. 주간·월간은 출력 방식에 따라 페이지가 확장됩니다.")
        print_data = {d: v for d, v in cached["data"].items() if include_empty or v["allday"] or v["timed"]}
        if not print_data:
            st.info("인쇄할 기록이 없습니다. 빈 날짜 인쇄를 선택하세요.")
        else:
            day_keys = list(selected_weeks) if layout.startswith(("월간","연간")) else [start_d] if layout.startswith("다년간") else sorted(print_data.keys()) if layout=="일간" else sorted({week_start(d) for d in print_data})
            st.subheader("📐 인쇄 레이아웃")
            st.caption("슬라이더를 바꾸면 아래 선택한 날짜의 **실제 PDF 미리보기**가 자동 갱신됩니다. 구글캘린더는 다시 조회하지 않습니다.")
            font_option = st.radio("본문 글자 크기", ["작게", "보통", "크게"], index=1, horizontal=True, key="v984_font_"+mode)
            FONT_SCALE = {"작게": 0.85, "보통": 1.0, "크게": 1.2}[font_option]
            st.caption("상세 기록 또는 주간 사건 제목에 적용됩니다. 날짜 머리글은 고정됩니다.")
            setting_cols = st.columns(3)
            with setting_cols[0]:
                side_margin_cm = st.slider("본문 좌우 여백 (cm)", 0.8, 3.5, 1.0, 0.1, key="v9821_month_margin_"+mode+layout.split()[0]) if layout.startswith(("월간","연간","다년간")) or (layout.startswith("주간") and "세로" in layout) else st.slider("본문 좌우 여백 (cm)", 1.5, 3.5, 2.4, 0.1)
            with setting_cols[1]:
                column_gap_cm = st.slider("2단 사이 간격 (cm)", 0.5, 1.5, 0.85, 0.05, disabled=layout!="일간")
            with setting_cols[2]:
                entry_gap_px = st.slider("엔트리 간격 (px)", 8, 30, 17, 1)
            st.caption("일간은 2단 본문만 조절합니다. 주간·월간은 용지 좌우 여백과 사건 간격을 조절합니다.")
            st.subheader("🔍 PDF 미리보기")
            date_key = "v981_preview_"+mode+layout
            if st.session_state.get(date_key) not in day_keys:
                st.session_state[date_key] = day_keys[0]
            def shift_preview_day(delta):
                idx = day_keys.index(st.session_state[date_key])
                st.session_state[date_key] = day_keys[max(0,min(len(day_keys)-1,idx+delta))]
                st.session_state["preview_page"] = 1
            if not layout.startswith("다년간"):
                left, middle, right = st.columns([1,3,1])
                with left:
                    st.button("◀ 전날" if layout=="일간" else "◀ 이전", disabled=st.session_state[date_key]==day_keys[0], on_click=shift_preview_day,args=(-1,))
                with right:
                    st.button("다음 날 ▶" if layout=="일간" else "다음 ▶", disabled=st.session_state[date_key]==day_keys[-1], on_click=shift_preview_day,args=(1,))
            else:
                middle = st.container()
            with middle:
                selected_day = st.selectbox(
                    "선택 기간" if layout.startswith("다년간") else "미리 볼 연도" if layout.startswith("연간") else "미리 볼 월" if layout.startswith("월간") else "미리 볼 날짜" if layout=="일간" else "미리 볼 주", day_keys,
                    format_func=lambda x: f"{start_d.year}~{end_d.year}년" if layout.startswith("다년간") else f"{x.year}년" if layout.startswith("연간") else f"{x.year}년 {x.month}월" if layout.startswith(("월간","연간","다년간")) else str(x) if layout=="일간" else f"{x} ~ {x+timedelta(days=6)}", key="v981_preview_"+mode+layout,
                )
            current_key = (
                str(selected_day), round(side_margin_cm, 2),
                round(column_gap_cm, 2), entry_gap_px, FONT_SCALE,
                id(cached["data"]), include_empty, mode, layout,
            )
            if st.session_state["preview_key"] != current_key:
                with st.spinner("변경된 설정으로 미리보기를 갱신하는 중..."):
                    try:
                        st.session_state["preview_pdf"] = render_body(
                            {d:v for d,v in print_data.items() if period_start(d,layout.split()[0])==selected_day} if layout.startswith(("월간","연간")) else print_data if layout.startswith("다년간") else {selected_day: cached["data"][selected_day]} if layout=="일간" else {d:v for d,v in print_data.items() if week_start(d)==selected_day},
                            cached["legend"], cached["ids"],
                            side_margin_cm, column_gap_cm, entry_gap_px, include_empty, FONT_SCALE, layout, planner=planner,
                        )
                        old_key = st.session_state["preview_key"]
                        if old_key is None or old_key[0] != current_key[0] or old_key[-1] != layout:
                            st.session_state["preview_page"] = 1
                        st.session_state["preview_key"] = current_key
                    except Exception as exc:
                        st.session_state["preview_pdf"] = None
                        st.error(f"미리보기 생성 오류: {type(exc).__name__}: {exc}")

            preview_bytes = st.session_state["preview_pdf"]
            if preview_bytes:
                try:
                    with fitz.open(stream=preview_bytes, filetype="pdf") as doc:
                        page_count = len(doc)
                        if layout.startswith(("주간","월간")) and page_count == 1:
                            st.session_state["preview_page"] = 1
                            st.caption(f"{day_keys.index(selected_day)+1} / {len(day_keys)}" + ("주 · 한 주당 한 페이지" if layout.startswith("주간") else "개월 · 한 달당 한 페이지"))
                        else:
                            st.caption(f"선택 기간: {page_count}페이지" + (" (다년간)" if layout.startswith("다년간") else " (첫 페이지는 시간표, 이후는 본문)" if layout=="일간" else " (연간)" if layout.startswith("연간") else " (월간)" if layout.startswith("월간") else " (한 주당 한 페이지)"))
                            if st.session_state["preview_page"] > page_count:
                                st.session_state["preview_page"] = page_count
                            previous, counter, following = st.columns([1, 2, 1])
                            def shift_page(delta, count):
                                st.session_state["preview_page"] = max(1,min(count,st.session_state["preview_page"]+delta))
                            with previous:
                                st.button("◀ 이전 페이지", disabled=st.session_state["preview_page"] <= 1, on_click=shift_page,args=(-1,page_count),key="preview_page_prev")
                            with following:
                                st.button("다음 페이지 ▶", disabled=st.session_state["preview_page"] >= page_count, on_click=shift_page,args=(1,page_count),key="preview_page_next")
                            with counter:
                                st.markdown(f"**{st.session_state['preview_page']} / {page_count} 페이지**")
                        page = doc.load_page(st.session_state["preview_page"] - 1)
                        pix = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5), alpha=False)
                        st.image(pix.tobytes("png"), use_container_width=True)
                except Exception as exc:
                    st.error(f"PDF 표시 오류: {type(exc).__name__}: {exc}")

            body_args = (print_data, cached["legend"], cached["ids"], side_margin_cm, column_gap_cm, entry_gap_px, include_empty, FONT_SCALE, layout)
            body_key = (mode, id(cached["data"]), side_margin_cm, column_gap_cm, entry_gap_px, FONT_SCALE, include_empty, layout)
            body_ready = cached["start"] == start_d and cached["end"] == end_d and cached.get("manual", manual) == manual

else:
    st.error("인증 정보를 불러오지 못했습니다.")

# --- [7. V97 photo appendix] ---
import io, hashlib, base64, html
from PIL import Image, ImageOps
try:
    from pillow_heif import register_heif_opener
    register_heif_opener()
except ImportError:
    pass

def read_photo(raw):
    with Image.open(io.BytesIO(raw)) as im:
        exif = im.getexif()
        nested = exif.get_ifd(34665) if 34665 in exif else {}
        stamp = None
        for value in (nested.get(36867), exif.get(36867), nested.get(36868), exif.get(36868)):
            if value:
                try:
                    stamp = datetime.strptime(str(value), '%Y:%m:%d %H:%M:%S')
                    break
                except ValueError:
                    pass
        im = ImageOps.exif_transpose(im)
        im.thumbnail((2400, 2400))
        if im.mode in ('RGBA','LA') or 'transparency' in im.info:
            rgba = im.convert('RGBA')
            white = Image.new('RGB', rgba.size, 'white')
            white.paste(rgba, mask=rgba.getchannel('A'))
            im = white
        else:
            im = im.convert('RGB')
        buf = io.BytesIO()
        im.save(buf, format='JPEG', quality=92)
        return stamp, buf.getvalue()

def photo_pdf(records, cols):
    esc = html.escape
    groups = {}
    for r in sorted(records, key=lambda r: (r['day'], r['stamp'] or datetime.max, r['name'])):
        groups.setdefault(r['day'], []).append(r)
    parts = ['<h1>사진 기록 부록</h1>']
    for day, items in groups.items():
        parts.append(f'<h2>{day}</h2>')
        for i in range(0, len(items), cols):
            cells = []
            for r in items[i:i+cols]:
                stamp = r['stamp'].strftime('%Y-%m-%d %H:%M') if r['stamp'] else '촬영일 미확인'
                b64 = base64.b64encode(r['jpeg']).decode('ascii')
                cells.append(f'<td><img src="data:image/jpeg;base64,{b64}"><div class="meta">{esc(stamp)}</div><div class="caption">{esc(r["caption"])}</div></td>')
            cells.extend(['<td></td>']*(cols-len(cells)))
            parts.append('<table><tr>'+''.join(cells)+'</tr></table>')
    height = {1:145,2:85,3:60,4:45}[cols]
    css = f'''@page {{size:A4;margin:18mm; @bottom-center {{content: "사진 부록 · " counter(page);font-size:8pt;}}}} body {{font-family:NanumGothic,sans-serif;color:#332c28;font-size:9pt;}} h1 {{font-size:19pt;margin:0 0 6mm;}} h2 {{font-size:12pt;border-bottom:1px solid #aaa; margin:4mm 0 2mm;break-after:avoid;}} table {{width:100%;table-layout:fixed;border-spacing:2mm;break-inside:avoid;}} td {{width:{100/cols}%;vertical-align:top;}} img {{display:block;max-width:100%;max-height:{height}mm;margin:auto;}} .meta {{font-size:8pt;color:#555;margin-top:1mm;}} .caption {{white-space:pre-wrap;overflow-wrap:break-word;}}'''
    return HTML(string='<html><meta charset="utf-8"><body>'+''.join(parts)+'</body></html>').write_pdf(stylesheets=[CSS(string=css)])

def merge_photo_pdf(diary, photos):
    with fitz.open(stream=diary,filetype='pdf') as a, fitz.open(stream=photos,filetype='pdf') as b:
        a.insert_pdf(b)
        return a.tobytes(garbage=3, deflate=True)

st.divider()
st.header(f'📷 {mode} 사진 기록 부록')
st.caption('일기와 플래너의 사진은 각각 따로 보관됩니다. 사진은 현재 세션에서 처리하며 클라우드 서버로 전송됩니다. 민감한 사진은 비공개 앱에서만 사용하세요.')
# Persist processed photos independently of transient uploader widgets.
prefix = 'v9802_'+mode+'_'
state = st.session_state.setdefault(prefix+'state', {})
active = state.setdefault('active', {})
settings = state.setdefault('settings', {})
files = st.file_uploader('사진 업로드', type=['jpg','jpeg','png','heic','heif','webp'], accept_multiple_files=True, key=prefix+'upload_'+str(state.get('upload_epoch',0)))
if files:
    for f in files:
        raw = f.getvalue()
        key = hashlib.sha256(raw).hexdigest()
        if key not in active:
            try:
                active[key] = (f.name, *read_photo(raw))
            except Exception as e:
                st.warning(f'{f.name}: 사진을 읽지 못했습니다 ({type(e).__name__})')
    state['upload_epoch'] = state.get('upload_epoch',0)+1
    st.rerun()
st.caption('업로드한 사진은 아래 목록에 보관됩니다. 삭제 버튼으로 제거할 수 있습니다.')
records = []
cols = state.get('cols',3)
signature = None
if active and st.button('사진 모두 삭제', key=prefix+'clear'):
    active.clear()
    settings.clear()
    state.pop('pdf',None)
    state.pop('sig',None)
    st.rerun()
if active:
    st.caption(f'{mode} 사진 {len(active)}장')
    cols = st.radio('사진 배열', [1,2,3,4], index=[1,2,3,4].index(state.get('cols',3)), horizontal=True, format_func=lambda x:f'{x}열', key=prefix+'cols')
    state['cols'] = cols
    records = []
    missing = sum(1 for key,(_,stamp,_) in active.items() if settings.get(key, {}).get('include',True) and settings.get(key, {}).get('day',stamp.date() if stamp else None) is None)
    if missing:
        st.warning(f'촬영일을 확인할 수 없는 사진 {missing}장이 있습니다. 아래에 펼쳐진 날짜 입력란에서 기록할 날짜를 지정하세요. 날짜 지정 전에는 해당 사진이 PDF에 포함되지 않습니다.')
    for key,(name,stamp,jpeg) in sorted(active.items(), key=lambda x:(x[1][1] or datetime.max,x[1][0])):
        saved = settings.setdefault(key, {'day':stamp.date() if stamp else None,'caption':'','include':True})
        with st.expander(name + ' · ' + (stamp.strftime('%Y-%m-%d %H:%M') if stamp else '촬영일 미확인'), expanded=saved['day'] is None):
            left,right = st.columns([1,2])
            with left:
                st.image(jpeg, width=140)
            with right:
                day = st.date_input('기록 귀속일 (사진을 넣을 날짜)', value=saved['day'], min_value=date(1900,1,1), max_value=date(2100,12,31), key=prefix+'day_'+key)
                caption = st.text_area('사진 설명', value=saved['caption'], key=prefix+'caption_'+key, max_chars=300)
                include = st.checkbox('출력에 포함', value=saved['include'], key=prefix+'include_'+key)
            if st.button('이 사진 삭제', key=prefix+'delete_'+key):
                active.pop(key,None)
                settings.pop(key,None)
                st.rerun()
            saved.update(day=day,caption=caption,include=include)
            if include and day is None:
                st.warning('위 날짜 입력란에서 기록 귀속일을 지정해 주세요.')
            if include and day is not None:
                records.append(dict(day=day, stamp=stamp, jpeg=jpeg, caption=caption, name=name, key=key))
    signature = (cols, tuple((r['key'],r['day'],r['caption']) for r in records))
    st.caption(f'PDF에 포함할 수 있는 사진: {len(records)}장 / {len(active)}장')
    if not records:
        st.info('날짜를 지정하고 출력에 포함할 사진을 선택하면 미리보기 버튼이 활성화됩니다.')
    if st.button('사진 부록 PDF 미리보기', key=prefix+'generate', disabled=not records):
        with st.spinner('사진 부록 생성 중...'):
            try:
                state['pdf'] = photo_pdf(records, cols)
                state['sig'] = signature
                state['page'] = 1
            except Exception as e:
                st.error(f'사진 PDF 생성 실패: {type(e).__name__}: {e}')
    photo_bytes = state.get('pdf')
    if records and photo_bytes and state.get('sig') == signature:
        with fitz.open(stream=photo_bytes,filetype='pdf') as doc:
            p = st.selectbox('사진 부록 페이지', list(range(1,len(doc)+1)), index=min(state.get('page',1),len(doc))-1, key=prefix+'page_'+hashlib.sha256(photo_bytes).hexdigest()[:16])
            state['page'] = p
            st.image(doc[p-1].get_pixmap(matrix=fitz.Matrix(1.5,1.5)).tobytes('png'),use_container_width=True)
    elif photo_bytes:
        st.info('사진 설정이 변경되었습니다. 미리보기 버튼을 다시 눌러주세요.')
else:
    for k in ('pdf','sig','combined','combined_sig','page'):
        state.pop(k,None)

# Unified export: each action generates its own current inputs.
st.divider()
st.header('📄 PDF 출력')
st.caption('원하는 출력 방식을 선택하세요. 다른 PDF를 먼저 만들 필요가 없습니다.')
if not body_ready:
    st.info(f'{mode} 본문을 출력하려면 현재 날짜와 캘린더 설정으로 먼저 기록을 불러오세요.')
if not records:
    st.caption('사진 부록을 출력하려면 사진을 추가하고 기록 날짜를 지정하세요.')
export_options = [
    ('body', f'{mode} PDF 생성', body_ready, body_key, 'Planner.pdf' if planner else 'MyDiary.pdf'),
    ('photos', '사진 부록 PDF 생성', bool(records), signature, 'PhotoAppendix.pdf'),
    ('combined', f'{mode} + 사진 부록 PDF 생성', body_ready and bool(records), (body_key, signature), 'PlannerWithPhotos.pdf' if planner else 'DiaryWithPhotos.pdf'),
]
exports = state.setdefault('exports', {})
for kind, label, ready, sig, filename in export_options:
    if st.button(label, key=prefix+'export_'+kind, disabled=not ready, use_container_width=True, type='primary' if kind=='combined' else 'secondary'):
        exports.pop(kind,None)
        try:
            with st.spinner('최신 설정으로 PDF를 생성하는 중입니다...'):
                if kind == 'body':
                    result = render_body(*body_args, planner=planner)
                elif kind == 'photos':
                    result = photo_pdf(records, cols)
                else:
                    result = merge_photo_pdf(render_body(*body_args, planner=planner), photo_pdf(records, cols))
                exports[kind] = (sig, result)
            st.success('PDF 생성 완료!')
        except Exception as e:
            st.error(f'PDF 생성 실패: {type(e).__name__}: {e}')
    if ready and kind in exports and exports[kind][0] == sig:
        st.download_button(label.replace('생성','다운로드'), exports[kind][1], file_name=filename, mime='application/pdf', key=prefix+'export_download_'+kind)
    elif kind in exports:
        exports.pop(kind,None)
