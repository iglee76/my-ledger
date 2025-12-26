import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import time

# --- 1. 페이지 설정 및 CSS 스타일링 ---
st.set_page_config(page_title="나만의 가계부", page_icon="🧾", layout="centered")

# 커스텀 CSS 적용
st.markdown("""
    <style>
    .block-container {
        max-width: 450px;
        padding-top: 2rem;
        padding-bottom: 5rem;
        margin: 0 auto;
    }
    
    /* 제목 박스 스타일 */
    .header-box {
        background-color: #2C3E50;
        padding: 20px;
        border-radius: 15px;
        text-align: center;
        margin-bottom: 20px;
        display: flex;
        align-items: center;
        justify-content: center;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
    }
    .header-text {
        font-size: 24px;
        font-weight: bold;
        color: white;
        margin-left: 15px;
        letter-spacing: 5px;
    }
    
    /* 현황판 스타일 */
    .dashboard-container {
        background-color: #F0F2F6;
        padding: 15px;
        border-radius: 15px;
        margin-bottom: 25px;
    }
    .dashboard-grid {
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 10px;
    }
    .stat-box {
        background-color: white;
        padding: 15px;
        border-radius: 12px;
        text-align: center;
        box-shadow: 0 2px 4px rgba(0,0,0,0.05);
    }
    .stat-label {
        font-size: 14px;
        color: #666;
        margin-bottom: 5px;
        font-weight: bold;
    }
    .stat-value {
        font-size: 18px;
        font-weight: bold;
        color: #333;
    }
    
    /* 입력 라벨 스타일 */
    .stSelectbox label, .stDateInput label, .stNumberInput label, .stTextArea label {
        font-weight: bold;
    }
    
    /* 버튼 스타일 */
    .stButton button {
        background-color: #1A5276;
        color: white;
        font-weight: bold;
        border-radius: 10px;
        border: none;
        transition: background-color 0.3s;
        font-size: 16px;
    }
    .stButton button:hover {
        background-color: #154360;
        color: #EAECEE;
    }

    /* Press Ctrl+Enter 문구 숨기기 */
    [data-testid="InputInstructions"] {
        display: none;
    }

    /* [핵심 수정] 모바일에서도 컬럼 강제 가로 정렬 */
    [data-testid="column"] {
        display: flex !important;
        flex-direction: column !important;
        min-width: 0px !important; /* 좁아도 줄바꿈 금지 */
    }
    
    /* 컬럼을 감싸는 부모 컨테이너가 줄바꿈 하지 않도록 설정 */
    [data-testid="stHorizontalBlock"] {
        flex-wrap: nowrap !important;
    }
    </style>
""", unsafe_allow_html=True)

# --- 2. 데이터 분류 정의 ---
CATEGORY_DATA = {
    "수입": {
        "고정수입": {
            "급여": ["노지혜 월급", "이일권 월급"]
        },
        "기타수입": {
            "기타소득": ["기타소득", "보험", "상생체크캐쉬백"],
            "상품권": ["상품권"]
        },
        "변동수입": {
            "급여": ["이일권 상여금"],
            "민생지원금": ["소비쿠폰"],
            "상생카드": ["KJ카드캐쉬백"],
            "상생페이백": ["디지털온누리상품권"],
            "앱테크": ["애드포스트"]
        }
    },
    "지출": {
        "변동지출": {
            "식비": ["간식", "식자재", "외식", "포장/배달"],
            "지원": ["부모님"],
            "건강": ["건강", "병원/약국"],
            "경조사": ["경조사비"],
            "교통비": ["대중교통", "차량관련"],
            "기타지출": ["기타지출"],
            "대출상환": ["아파트 원금", "아파트 이자"],
            "문화": ["등산", "여가생활", "여행", "카페", "캠핑"],
            "미용": ["의류/헤어", "화장품"],
            "생활비": ["생활용품"],
            "세금": ["세금"],
            "숙박비": ["숙소"]
        },
        "자녀지출": {
            "교육비": ["둘째교육", "막내교육", "첫째교육"],
            "자녀기타": ["둘째기타", "막내기타", "첫째기타"]
        }
    },
    "저축": {
        "단기": {
            "적금": ["여행대비", "의료비(단기)"]
        },
        "장기": {
            "예금": ["노후대비", "의료비(장기)"]
        }
    },
    "투자": {
        "연금": {
            "개인연금저축": ["노지혜 연금", "이일권 연금"]
        },
        "주식": {
            "주식": ["노지혜주식"]
        },
        "IRP": {
            "개인퇴직연금": ["노지혜 IRP", "이일권 IRP"]
        },
        "ISA": {
            "자산관리": ["노지혜 ISA"]
        }
    }
}

PAYMENT_METHODS = [
    "현대카드(이)", "현대카드(노)", "하나카드(노)", "광주체크카드(노)", 
    "남구동행카드", "현금", "소비쿠폰(이)", "소비쿠폰(노)", 
    "디지털온누리(이)", "디지털온누리(노)", "상생카드(이)", 
    "상생카드(노)", "선불카드", "상품권"
]

# --- 3. 구글 시트 연결 및 데이터 로딩 ---
@st.cache_resource
def get_google_sheet_client():
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    creds = ServiceAccountCredentials.from_json_keyfile_dict(st.secrets["google_auth"], scope)
    client = gspread.authorize(creds)
    return client

@st.cache_data(ttl=60)
def load_dashboard_data(month_name):
    try:
        client = get_google_sheet_client()
        sheet_url = st.secrets["spreadsheet"]["url"]
        doc = client.open_by_url(sheet_url)
        worksheet = doc.worksheet(month_name)
        
        data = worksheet.get_all_values()
        
        income = expense = saving = invest = 0
        
        if len(data) > 3:
            df = pd.DataFrame(data[3:], columns=data[2])
            df.iloc[:, 7] = df.iloc[:, 7].astype(str).str.replace(',', '').str.replace('₩', '').str.replace(' ', '')
            df.iloc[:, 7] = pd.to_numeric(df.iloc[:, 7], errors='coerce').fillna(0)
            
            income = df[df.iloc[:, 3] == "수입"].iloc[:, 7].sum()
            expense = df[df.iloc[:, 3] == "지출"].iloc[:, 7].sum()
            saving = df[df.iloc[:, 3] == "저축"].iloc[:, 7].sum()
            invest = df[df.iloc[:, 3] == "투자"].iloc[:, 7].sum()
            
        return int(income), int(expense), int(saving), int(invest)
        
    except Exception as e:
        return 0, 0, 0, 0

# --- 4. 초기화 및 상태 관리 ---
if "form_key" not in st.session_state:
    st.session_state.form_key = 0

def reset_mid_sub_detail():
    st.session_state[f"mid_cat_{st.session_state.form_key}"] = None
    st.session_state[f"sub_cat_{st.session_state.form_key}"] = None
    st.session_state[f"detail_cat_{st.session_state.form_key}"] = None

def reset_sub_detail():
    st.session_state[f"sub_cat_{st.session_state.form_key}"] = None
    st.session_state[f"detail_cat_{st.session_state.form_key}"] = None

def reset_detail():
    st.session_state[f"detail_cat_{st.session_state.form_key}"] = None

# --- 5. 메인 UI 구성 ---

st.markdown("""
    <div class="header-box">
        <img src="https://i.ibb.co/1JJn62dv/account512.png" width="50" height="50">
        <span class="header-text">가 계 부</span>
    </div>
""", unsafe_allow_html=True)

current_month_name = f"{datetime.now().month}월"
income, expense, saving, invest = load_dashboard_data(current_month_name)

st.markdown(f"""
    <div class="dashboard-container">
        <div class="dashboard-grid">
            <div class="stat-box">
                <div class="stat-label">💰 이번 달 수입</div>
                <div class="stat-value" style="color: #4CAF50;">+{income:,}</div>
            </div>
            <div class="stat-box">
                <div class="stat-label">💸 이번 달 지출</div>
                <div class="stat-value" style="color: #F44336;">-{expense:,}</div>
            </div>
            <div class="stat-box">
                <div class="stat-label">🐷 이번 달 저축</div>
                <div class="stat-value" style="color: #2196F3;">{saving:,}</div>
            </div>
            <div class="stat-box">
                <div class="stat-label">📈 이번 달 투자</div>
                <div class="stat-value" style="color: #FF9800;">{invest:,}</div>
            </div>
        </div>
    </div>
""", unsafe_allow_html=True)

# --- 6. 입력 폼 ---
current_key = st.session_state.form_key

with st.container(border=True):
    # 1행: 비율 [1.2, 1, 1.8]
    c1, c2, c3 = st.columns([1.2, 1, 1.8]) 
    
    with c1:
        input_date = st.date_input("📅 사용일자", datetime.now(), key=f"date_{current_key}")
    with c2:
        input_amount = st.number_input("💰 금액 (₩)", value=None, placeholder="0", min_value=0, step=1000, format="%d", key=f"amount_{current_key}")
    with c3:
        input_payment = st.selectbox("💳 결제수단", PAYMENT_METHODS, index=None, placeholder="선택", key=f"payment_{current_key}")

    # 2행
    c4, c5 = st.columns(2)
    with c4:
        main_cats = list(CATEGORY_DATA.keys())
        selected_main = st.selectbox("📂 대분류", main_cats, index=None, placeholder="선택", 
                                   key=f"main_cat_{current_key}", on_change=reset_mid_sub_detail)
    
    with c5:
        if selected_main:
            mid_cats = list(CATEGORY_DATA[selected_main].keys())
        else:
            mid_cats = []
        selected_mid = st.selectbox("🗂️ 중분류", mid_cats, index=None, placeholder="선택", 
                                  key=f"mid_cat_{current_key}", on_change=reset_sub_detail)

    # 3행
    c6, c7 = st.columns(2)
    with c6:
        if selected_main and selected_mid:
            sub_cats = list(CATEGORY_DATA[selected_main][selected_mid].keys())
        else:
            sub_cats = []
        selected_sub = st.selectbox("📑 소분류", sub_cats, index=None, placeholder="선택", 
                                  key=f"sub_cat_{current_key}", on_change=reset_detail)
        
    with c7:
        if selected_main and selected_mid and selected_sub:
            detail_cats = CATEGORY_DATA[selected_main][selected_mid][selected_sub]
        else:
            detail_cats = []
        selected_detail = st.selectbox("🔖 상세", detail_cats, index=None, placeholder="선택", key=f"detail_cat_{current_key}")

    # 4행
    input_desc = st.text_area("📝 내역", placeholder="기타 메모 사항을 입력하세요", height=80, key=f"desc_{current_key}")

    submit_btn = st.button("➕ 기록하기", use_container_width=True)

# --- 7. 저장 로직 ---
if submit_btn:
    if input_amount is None:
        st.warning("금액을 입력해주세요.")
    elif not input_payment:
        st.warning("결제수단을 선택해주세요.")
    elif not selected_main:
        st.warning("대분류를 선택해주세요.")
    elif not selected_mid:
        st.warning("중분류를 선택해주세요.")
    elif not selected_sub:
        st.warning("소분류를 선택해주세요.")
    elif not selected_detail:
        st.warning("상세 항목을 선택해주세요.")
    else:
        try:
            status_msg = st.empty()
            status_msg.info("저장 중입니다...")

            client = get_google_sheet_client()
            sheet_url = st.secrets["spreadsheet"]["url"]
            doc = client.open_by_url(sheet_url)
            
            target_month_name = f"{input_date.month}월"
            ws = doc.worksheet(target_month_name)
            
            col_c_values = ws.col_values(3)
            next_row = len(col_c_values) + 1
            if next_row < 21: next_row = 21
            
            updates = [
                {'range': f'C{next_row}', 'values': [[str(input_date)]]},
                {'range': f'D{next_row}', 'values': [[selected_main]]},
                {'range': f'G{next_row}', 'values': [[selected_detail]]},
                {'range': f'H{next_row}', 'values': [[input_amount]]},
                {'range': f'I{next_row}', 'values': [[input_payment]]},
                {'range': f'J{next_row}', 'values': [[input_desc]]}
            ]
            
            ws.batch_update(updates)
            
            st.session_state.form_key += 1
            load_dashboard_data.clear()
            
            st.success(f"{target_month_name} 시트에 저장되었습니다! 🎉")
            time.sleep(1)
            st.rerun()
            
        except gspread.exceptions.WorksheetNotFound:
            st.error(f"'{target_month_name}' 시트가 없습니다.")
        except Exception as e:
            st.error(f"저장 중 오류: {e}")