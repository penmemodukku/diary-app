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
