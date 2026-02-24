"""
서울 아파트 검색 앱 (Streamlit)
"""
import os
import re
from difflib import SequenceMatcher

import pandas as pd
import streamlit as st
import folium
from streamlit_folium import st_folium

from crawler import SeoulApartmentCrawler
from utils import extract_dong

# 새로 수집한 데이터를 세션에 넣어두는 키 (Cloud에서 파일 저장이 안 돼도 새로고침 반영)
SESSION_KEY_APARTMENT_DATA = "apartment_data"
# 메인 아파트(실거래가) 단지명 유사도 매칭 임계값 (0~1)
MAIN_APT_SIMILARITY_THRESHOLD = 0.85


def normalize_dong(dong):
    """동 표기 정규화: '역삼2동' → '역삼동', '삼성1동' → '삼성동' (숫자 제거)."""
    if dong is None or (isinstance(dong, float) and pd.isna(dong)):
        return ""
    s = str(dong).strip()
    if not s:
        return ""
    return re.sub(r"\d+동$", "동", s)


def normalize_apt(name):
    """단지명 정규화: 공백 collapse, 앞뒤 공백 제거."""
    if name is None or (isinstance(name, float) and pd.isna(name)):
        return ""
    return " ".join(str(name).strip().split())


def enrich_with_main_apt(df: pd.DataFrame, main_path: str) -> pd.DataFrame:
    """
    메인 아파트 CSV와 동 정규화 + 단지명 유사도 매칭으로 left join.
    매칭되면 평수, 실거래가, 기준연월일 컬럼 추가; 안 되면 공란.
    """
    if not os.path.exists(main_path) or df.empty:
        return df
    try:
        main = pd.read_csv(main_path, encoding="utf-8-sig")
        main = main[["구", "동", "아파트명", "평수", "실거래가", "기준연월일"]].drop_duplicates(
            subset=["구", "동", "아파트명"], keep="first"
        )
    except Exception:
        return df
    main["norm_동"] = main["동"].apply(normalize_dong)
    main["norm_아파트명"] = main["아파트명"].apply(normalize_apt)
    # (구, norm_동)별 후보 리스트
    main_by_key = {}
    for _, row in main.iterrows():
        key = (row["구"], row["norm_동"])
        if key not in main_by_key:
            main_by_key[key] = []
        main_by_key[key].append(row)

    df = df.copy()
    df["평수"] = None
    df["실거래가"] = None
    df["기준연월일"] = None
    if "자치구" not in df.columns or "동" not in df.columns or "아파트명" not in df.columns:
        return df
    for i in df.index:
        gu = df.at[i, "자치구"]
        dong = df.at[i, "동"]
        apt = df.at[i, "아파트명"]
        norm_dong = normalize_dong(dong)
        norm_apt = normalize_apt(apt)
        candidates = main_by_key.get((gu, norm_dong), [])
        if not candidates:
            continue
        best = max(
            candidates,
            key=lambda c: SequenceMatcher(None, norm_apt, c["norm_아파트명"]).ratio(),
        )
        sim = SequenceMatcher(None, norm_apt, best["norm_아파트명"]).ratio()
        if sim >= MAIN_APT_SIMILARITY_THRESHOLD:
            df.at[i, "평수"] = best["평수"]
            df.at[i, "실거래가"] = best["실거래가"]
            df.at[i, "기준연월일"] = best["기준연월일"]
    return df


def preprocess_apartment_df(df: pd.DataFrame) -> pd.DataFrame:
    """CSV/API에서 읽은 df에 동일한 전처리(동 추가, 임대·오피스텔 제외 등) 적용."""
    if df.empty:
        return df
    df = df.copy()
    if "동" not in df.columns:
        if "원본_EMD_ADDR" in df.columns:
            df["동"] = df["원본_EMD_ADDR"].apply(
                lambda x: str(x).strip() if pd.notna(x) and str(x).strip() and str(x).strip() != "nan" else None
            )
        else:
            df["동"] = df["주소"].apply(extract_dong)
    if "아파트명" in df.columns:
        df = df[~df["아파트명"].astype(str).str.contains("임대", na=False)]
    if "원본_CMPX_CLSF" in df.columns:
        df = df[df["원본_CMPX_CLSF"].astype(str).str.contains("아파트", na=False)]
    if "아파트명" in df.columns:
        df = df[~df["아파트명"].astype(str).str.contains("오피스텔", na=False, case=False)]
    if "동" in df.columns:
        df["동"] = df["동"].replace("답십리1동", "답십리동")
    return df


# 페이지 설정
st.set_page_config(
    page_title="서울 아파트 검색",
    page_icon="🏢",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 제목
# st.title("🏢 서울 아파트 검색 시스템")
# st.markdown("---")

# 데이터 로드 함수
@st.cache_data
def load_data():
    """데이터 로드 (캐싱). 세션에 새로 수집한 데이터가 있으면 최우선 사용."""
    # 1) 새로고침으로 수집한 데이터가 세션에 있으면 그대로 사용 (Cloud에서 파일 저장 안 돼도 동작)
    if SESSION_KEY_APARTMENT_DATA in st.session_state:
        df = st.session_state[SESSION_KEY_APARTMENT_DATA]
        if df is not None and not df.empty:
            return df, "metadata", len(df)

    crawler = SeoulApartmentCrawler()
    # 2) CSV 또는 샘플
    if os.path.exists("seoul_apartments_metadata.csv"):
        df = crawler.load_from_csv("seoul_apartments_metadata.csv")
        data_type = "metadata"
    elif os.path.exists("seoul_apartments.csv"):
        df = crawler.load_from_csv("seoul_apartments.csv")
        data_type = "sample" if "아파트명" not in df.columns else "normal"
    else:
        df = crawler.generate_sample_data(num_samples=500)
        crawler.save_to_csv(df, "seoul_apartments.csv")
        data_type = "generated"

    df = preprocess_apartment_df(df)
    return df, data_type, len(df)


# 데이터 로드
df, data_type, data_count = load_data()

# 데이터 로드 메시지 표시 (캐시 함수 밖에서)
if data_type == "metadata":
    st.toast(f"실제 아파트 메타데이터 로드 완료 ({data_count}건)", icon="✅")
elif data_type == "sample":
    st.toast("샘플 데이터를 사용 중입니다.", icon="⚠️")
elif data_type == "generated":
    st.toast("데이터 파일이 없습니다. 샘플 데이터를 생성합니다...", icon="ℹ️")

# 동 정보 추가 (없으면 생성)
if "동" not in df.columns:
    df["동"] = df["주소"].apply(extract_dong)

# 메인 아파트(실거래가) CSV와 동 정규화 + 단지명 유사도 매칭으로 평수/실거래가/기준연월일 추가
df = enrich_with_main_apt(df, "seoul_disrict_main_apt.csv")

# 사이드바 필터
st.sidebar.header("🔍 검색 필터")

# 초기화 버튼 (자치구 제외하고 모든 필터 초기화)
if st.sidebar.button("🔄 필터 초기화", width="stretch"):
    # 필터 관련 session_state 키들 초기화 (자치구 제외)
    filter_keys = ['dong', 'year_range', 'household', 'hallway', 'distance', 'subway']
    for key in filter_keys:
        if key in st.session_state:
            del st.session_state[key]
    st.rerun()

# 자치구와 동 필터 (병렬 배치)
col_district, col_dong = st.sidebar.columns(2)

with col_district:
    districts_list = df["자치구"].dropna().unique().tolist()
    districts = ["전체"] + sorted([str(x) for x in districts_list if pd.notna(x) and str(x).strip()])
    # 기본값을 동대문구로 설정 (동대문구가 있으면)
    default_district = "동대문구" if "동대문구" in districts else "전체"
    selected_district = st.selectbox("자치구", districts, index=districts.index(default_district) if default_district in districts else 0)

with col_dong:
    # 동 필터 (자치구 선택 시 해당 자치구의 동만 표시) - 동적 갱신
    if selected_district != "전체":
        district_df = df[df["자치구"] == selected_district]
        dong_list = district_df["동"].dropna().unique().tolist()
        dongs = ["전체"] + sorted([str(x) for x in dong_list if pd.notna(x) and str(x).strip()])
    else:
        dong_list = df["동"].dropna().unique().tolist()
        dongs = ["전체"] + sorted([str(x) for x in dong_list if pd.notna(x) and str(x).strip()])
    
    # 초기화 시 동은 "전체"로
    selected_dong = st.selectbox("동", dongs, index=0, key="dong")

# 필터링된 데이터 기준으로 슬라이더 범위 계산 (자치구 > 동 순서로 동적 갱신)
if selected_district != "전체":
    filter_base = df[df["자치구"] == selected_district]
    if selected_dong != "전체":
        filter_base = filter_base[filter_base["동"] == selected_dong]
else:
    filter_base = df.copy()

# 건축연도 필터 (필터링된 데이터 기준) - 동적 갱신
year_data = filter_base["건축연도"].dropna()
if len(year_data) > 0:
    min_year = int(year_data.min())
    max_year = int(year_data.max())
    # 초기화 시 전체 범위로
    default_year_range = (min_year, max_year)
    year_range = st.sidebar.slider(
        "건축연도 범위",
        min_value=min_year,
        max_value=max_year,
        value=default_year_range,
        step=1,
        key="year_range"
    )
else:
    year_range = (1900, 2025)

# 세대수 필터 (슬라이더) - 동적 갱신, 기본 최소 300세대 이상
household_data = filter_base["세대수"].dropna()
if len(household_data) > 0:
    min_household = int(household_data.min())
    max_household = int(household_data.max())
    default_household_low = min(max(300, min_household), max_household)
    default_household_range = (default_household_low, max_household)
    household_range = st.sidebar.slider(
        "세대수 범위",
        min_value=min_household,
        max_value=max_household,
        value=default_household_range,
        step=100,
        key="household"
    )
else:
    household_range = (0, 10000)

# 복도/계단식 필터 - 동적 갱신
hallway_types_list = filter_base["복도계단식"].dropna().unique().tolist()
hallway_types = ["전체"] + sorted([str(x) for x in hallway_types_list if pd.notna(x)])
# 초기화 시 "전체"로
selected_hallway = st.sidebar.selectbox("복도/계단식", hallway_types, index=0, key="hallway")

# 평형 필터 제거 (사용자 요청)

# 지하철역 거리 필터 (슬라이더) - 동적 갱신
distance_data = filter_base["지하철역거리_km"].dropna()
if len(distance_data) > 0:
    min_distance = float(distance_data.min())
    max_distance = float(distance_data.max())
    # 초기화 시 전체 범위로
    default_distance_range = (min_distance, max_distance)
    distance_range = st.sidebar.slider(
        "지하철역 거리 범위 (km)",
        min_value=min_distance,
        max_value=max_distance,
        value=default_distance_range,
        step=0.01,
        format="%.2f",
        key="distance"
    )
else:
    distance_range = (0.0, 10.0)

# 지하철역 선택 필터 (자치구/동 선택 시 해당 지역 내 지하철역만 표시) - 동적 갱신
if selected_district != "전체":
    # 선택된 자치구에 해당하는 데이터만 필터링
    district_df = df[df["자치구"] == selected_district]
    if selected_dong != "전체":
        district_df = district_df[district_df["동"] == selected_dong]
    subway_stations_list = district_df["가장가까운지하철역"].dropna().unique().tolist()
else:
    # 전체 데이터에서 지하철역 목록 가져오기
    subway_stations_list = df["가장가까운지하철역"].dropna().unique().tolist()

# 가나다순 정렬 (한글 정렬)
subway_stations = ["전체"] + sorted(
    [str(x) for x in subway_stations_list if pd.notna(x) and str(x).strip()],
    key=lambda x: x  # 한글은 기본 정렬로 가나다순 정렬됨
)
# 초기화 시 "전체"로
selected_subway = st.sidebar.selectbox("가장 가까운 지하철역", subway_stations, index=0, key="subway")

# 필터 적용
filtered_df = df.copy()

if selected_district != "전체":
    filtered_df = filtered_df[filtered_df["자치구"] == selected_district]

# 동 필터 적용
if selected_dong != "전체":
    filtered_df = filtered_df[filtered_df["동"] == selected_dong]

# 건축연도 필터 (NaN 값 처리)
if len(year_data) > 0:
    filtered_df = filtered_df[
        (filtered_df["건축연도"].notna()) &
        (filtered_df["건축연도"] >= year_range[0]) &
        (filtered_df["건축연도"] <= year_range[1])
    ]

# 세대수 필터 (NaN 값 처리) - 슬라이더 범위 적용
if len(household_data) > 0:
    filtered_df = filtered_df[
        (filtered_df["세대수"].notna()) &
        (filtered_df["세대수"] >= household_range[0]) &
        (filtered_df["세대수"] <= household_range[1])
    ]

if selected_hallway != "전체":
    filtered_df = filtered_df[filtered_df["복도계단식"] == selected_hallway]

# 평형 필터 제거 (사용자 요청)

# 지하철역 거리 필터 (NaN 값 처리) - 슬라이더 범위 적용
if len(distance_data) > 0:
    filtered_df = filtered_df[
        (filtered_df["지하철역거리_km"].notna()) &
        (filtered_df["지하철역거리_km"] >= distance_range[0]) &
        (filtered_df["지하철역거리_km"] <= distance_range[1])
    ]

if selected_subway != "전체":
    filtered_df = filtered_df[filtered_df["가장가까운지하철역"] == selected_subway]

# 결과 표시
st.write(f"📊 검색 결과: {len(filtered_df)}개")

if len(filtered_df) > 0:
    # 통계 정보
    col1, col2, col3, col4, col5 = st.columns(5)
    
    with col1:
        year_data = filtered_df['건축연도'].dropna()
        if len(year_data) > 0:
            st.metric("평균 건축연도", f"{int(year_data.mean())}년")
        else:
            st.metric("평균 건축연도", "N/A")
    with col2:
        household_data = filtered_df['세대수'].dropna()
        if len(household_data) > 0:
            st.metric("평균 세대수", f"{int(household_data.mean())}세대")
        else:
            st.metric("평균 세대수", "N/A")
    with col3:
        # 세대당 평균 평형 표시
        if "세대당평균평형" in filtered_df.columns:
            avg_pyeong_data = filtered_df["세대당평균평형"].dropna()
            if len(avg_pyeong_data) > 0:
                st.metric("평균 평형 (세대당)", f"{avg_pyeong_data.mean():.1f}평")
            else:
                # 세대당평균평형이 없으면 평형 컬럼 사용
                if "평형" in filtered_df.columns:
                    pyeong_data = filtered_df["평형"].dropna()
                    if len(pyeong_data) > 0:
                        st.metric("평균 평형", f"{pyeong_data.mean():.1f}평")
                    else:
                        st.metric("평균 평형", "N/A")
                else:
                    st.metric("평균 평형", "N/A")
        else:
            # 세대당평균평형 컬럼이 없으면 평형 컬럼 사용
            if "평형" in filtered_df.columns:
                pyeong_data = filtered_df["평형"].dropna()
                if len(pyeong_data) > 0:
                    st.metric("평균 평형", f"{pyeong_data.mean():.1f}평")
                else:
                    st.metric("평균 평형", "N/A")
            else:
                st.metric("평균 평형", "N/A")
    with col4:
        if "주차대수" in filtered_df.columns:
            parking_data = filtered_df["주차대수"].dropna()
            # 주차대수가 0인 경우도 포함 (0은 유효한 값)
            parking_data = parking_data[parking_data >= 0]  # 음수 제외만
            if len(parking_data) > 0:
                st.metric("평균 주차대수", f"{int(parking_data.mean())}대")
            else:
                st.metric("평균 주차대수", "N/A")
        else:
            st.metric("평균 주차대수", "N/A")
    with col5:
        if "세대당주차면수" in filtered_df.columns:
            parking_per_hh_data = filtered_df["세대당주차면수"].dropna()
            if len(parking_per_hh_data) > 0:
                st.metric("평균 세대당 주차면수", f"{parking_per_hh_data.mean():.2f}면")
            else:
                st.metric("평균 세대당 주차면수", "N/A")
        else:
            distance_data = filtered_df["지하철역거리_km"].dropna()
            if len(distance_data) > 0:
                st.metric("평균 지하철 거리", f"{distance_data.mean():.2f}km")
            else:
                st.metric("평균 지하철 거리", "N/A")
    
    st.markdown("---")
    
    # 탭 생성
    tab1, tab2, tab3 = st.tabs(["📋 목록", "🗺️ 지도", "📈 통계"])
    
    with tab1:
        # 기본 정렬: 건축연도 오름차순 (오래된순)
        if "건축연도" in filtered_df.columns:
            sorted_df = filtered_df.sort_values(
                by="건축연도",
                ascending=True,
                na_position='last'  # NaN 값은 맨 뒤로
            )
        else:
            sorted_df = filtered_df.copy()
        
        # 데이터프레임 표시 (화면 출력용 컬럼만 필터링)
        # 원본 데이터는 모두 저장되어 있지만, 화면에는 필요한 컬럼만 표시
        display_columns = []
        
        # 기본 정보
        if "자치구" in sorted_df.columns:
            display_columns.append("자치구")
        if "동" in sorted_df.columns:
            display_columns.append("동")
        if "아파트명" in sorted_df.columns:
            display_columns.append("아파트명")
        if "건축연도" in sorted_df.columns:
            display_columns.append("건축연도")
        if "세대수" in sorted_df.columns:
            display_columns.append("세대수")
        if "복도계단식" in sorted_df.columns:
            display_columns.append("복도계단식")
        
        # 면적 정보 (세대당 평균만 표시)
        if "세대당평균평형" in sorted_df.columns:
            display_columns.append("세대당평균평형")
        # 메인 아파트 실거래가 (동·단지명 정규화+유사도 매칭, 없으면 공란)
        if "평수" in sorted_df.columns:
            display_columns.append("평수")
        if "실거래가" in sorted_df.columns:
            display_columns.append("실거래가")
        if "기준연월일" in sorted_df.columns:
            display_columns.append("기준연월일")
        # 전용면적별 세대현황 (평형별 세대수 분포)
        if "전용면적60㎡이하_세대수" in sorted_df.columns:
            display_columns.append("전용면적60㎡이하_세대수")
        if "전용면적60_85㎡_세대수" in sorted_df.columns:
            display_columns.append("전용면적60_85㎡_세대수")
        if "전용면적85_135㎡_세대수" in sorted_df.columns:
            display_columns.append("전용면적85_135㎡_세대수")
        
        # 주차 정보
        if "주차대수" in sorted_df.columns:
            display_columns.append("주차대수")
        if "세대당주차면수" in sorted_df.columns:
            display_columns.append("세대당주차면수")
        
        # 지하철 정보
        if "가장가까운지하철역" in sorted_df.columns:
            display_columns.append("가장가까운지하철역")
        if "지하철역거리_km" in sorted_df.columns:
            display_columns.append("지하철역거리_km")
        
        # 주소는 맨 우측에 배치
        if "주소" in sorted_df.columns:
            display_columns.append("주소")
        
        # 존재하는 컬럼만 필터링
        display_columns = [col for col in display_columns if col in sorted_df.columns]
        
        # 표시용 데이터프레임 생성 (컬럼명 간략화 및 포맷팅)
        display_df = sorted_df[display_columns].copy()
        
        # 컬럼명 간략화 매핑
        column_mapping = {
            "자치구": "자치구",
            "동": "동",
            "아파트명": "아파트명",
            "주소": "주소",
            "건축연도": "연도",
            "세대수": "세대수",
            "복도계단식": "복도/계단",
            "세대당평균평형": "평형",
            "평수": "평수",
            "실거래가": "실거래가",
            "기준연월일": "기준연월일",
            "전용면적60㎡이하_세대수": "60㎡이하",
            "전용면적60_85㎡_세대수": "60~85㎡",
            "전용면적85_135㎡_세대수": "85~135㎡",
            "주차대수": "주차",
            "세대당주차면수": "세대당주차",
            "가장가까운지하철역": "지하철역",
            "지하철역거리_km": "역거리"
        }
        
        # 컬럼명 변경
        display_df = display_df.rename(columns=column_mapping)
        # 매칭 안 된 행: 평수/실거래가/기준연월일 공란 처리
        for _col in ["평수", "실거래가", "기준연월일"]:
            if _col in display_df.columns:
                display_df[_col] = display_df[_col].apply(lambda x: "" if pd.isna(x) else x)
        # 건축연도 포맷팅 (콤마 제거, 정수로 표시)
        if "연도" in display_df.columns:
            display_df["연도"] = display_df["연도"].apply(
                lambda x: str(int(x)) if pd.notna(x) else ""
            )
        
        st.dataframe(
            display_df,
            width="stretch",
            height=700,
            hide_index=True
        )
        
        # CSV 다운로드 버튼 (간략화된 컬럼명으로)
        csv = display_df.to_csv(index=False, encoding='utf-8-sig')
        st.download_button(
            label="📥 CSV 다운로드",
            data=csv,
            file_name="seoul_apartments_filtered.csv",
            mime="text/csv"
        )
    
    with tab2:
        # 지도 생성
        if len(filtered_df) > 0:
            # 필터링된 데이터의 유효한 좌표만 사용하여 중심점 계산
            valid_coords = filtered_df[
                (filtered_df["위도"].notna()) & 
                (filtered_df["경도"].notna())
            ]
            
            if len(valid_coords) > 0:
                # 중심점 계산
                center_lat = valid_coords["위도"].mean()
                center_lon = valid_coords["경도"].mean()
                
                # 데이터 범위 계산
                min_lat = valid_coords["위도"].min()
                max_lat = valid_coords["위도"].max()
                min_lon = valid_coords["경도"].min()
                max_lon = valid_coords["경도"].max()
                
                # 범위에 따른 적절한 초기 줌 레벨 계산
                lat_range = max_lat - min_lat
                lon_range = max_lon - min_lon
                max_range = max(lat_range, lon_range)
                
                # 범위에 따른 적절한 줌 레벨 계산
                if max_range < 0.01:  # 매우 좁은 범위 (약 1km)
                    zoom_start = 15
                elif max_range < 0.05:  # 좁은 범위 (약 5km)
                    zoom_start = 13
                elif max_range < 0.1:  # 중간 범위 (약 10km)
                    zoom_start = 12
                elif max_range < 0.2:  # 넓은 범위 (약 20km)
                    zoom_start = 11
                else:  # 매우 넓은 범위
                    zoom_start = 10
            else:
                # 유효한 좌표가 없으면 서울 중심 좌표 사용
                center_lat = 37.5665
                center_lon = 126.9780
                zoom_start = 11
                min_lat = max_lat = min_lon = max_lon = None
            
            m = folium.Map(
                location=[center_lat, center_lon],
                zoom_start=zoom_start,
                tiles="OpenStreetMap"
            )
            
            # 마커 추가 (유효한 좌표만)
            for idx, row in filtered_df.iterrows():
                # 좌표가 유효한 경우에만 마커 추가
                if pd.notna(row.get("위도")) and pd.notna(row.get("경도")):
                    # 아파트명이 있으면 포함
                    apt_name = row.get('아파트명', '') or row.get('주소', '')
                    popup_text = f"""
                    <b>{apt_name}</b><br>
                    주소: {row.get('주소', '')}<br>
                    자치구: {row.get('자치구', '')}<br>
                    건축연도: {row.get('건축연도', '')}년<br>
                    세대수: {row.get('세대수', '')}세대<br>
                    평형: {row.get('평형', '')}평<br>
                    지하철역: {row.get('가장가까운지하철역', '')} ({row.get('지하철역거리_km', '')}km)
                    """
                    
                    # 툴팁에 아파트명 또는 주소 표시
                    tooltip_text = row.get('아파트명', '') or row.get('주소', '')
                    folium.Marker(
                        [row["위도"], row["경도"]],
                        popup=folium.Popup(popup_text, max_width=300),
                        tooltip=tooltip_text
                    ).add_to(m)
            
            # 모든 마커가 보이도록 bounds 설정 (유효한 좌표가 있는 경우만)
            if len(valid_coords) > 0 and min_lat is not None:
                padding = 0.01  # 약 1km 여유 공간
                m.fit_bounds(
                    [[min_lat - padding, min_lon - padding],
                     [max_lat + padding, max_lon + padding]],
                    padding=(20, 20)  # 픽셀 단위 여유 공간
                )
            
            # 지도 중앙 정렬을 위한 컬럼 사용
            col1, col2, col3 = st.columns([1, 10, 1])
            with col2:
                st_folium(m, height=600, width="stretch")
        else:
            st.info("표시할 데이터가 없습니다.")
    
    with tab3:
        st.info("💡 통계는 필터링과 무관하게 전체 데이터 기준으로 표시됩니다.")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.write("**자치구별 아파트 수**")
            # 전체 데이터 기준
            district_counts = df["자치구"].value_counts()
            st.bar_chart(district_counts)
        
        with col2:
            st.write("**건축연도별 분포**")
            # 전체 데이터 기준
            year_data = df["건축연도"].dropna()
            if len(year_data) > 0:
                year_counts = year_data.value_counts().sort_index()
                st.line_chart(year_counts)
        
        col3, col4 = st.columns(2)
        
        with col3:
            st.write("**복도/계단식 분포**")
            # 전체 데이터 기준
            hallway_data = df["복도계단식"].dropna()
            if len(hallway_data) > 0:
                hallway_counts = hallway_data.value_counts()
                st.bar_chart(hallway_counts)
        
        with col4:
            st.write("**세대당 평형 분포**")
            # 전체 데이터 기준
            if "세대당평균평형" in df.columns:
                pyeong_data = df["세대당평균평형"].dropna()
                if len(pyeong_data) > 0:
                    pyeong_counts = pd.cut(
                        pyeong_data,
                        bins=10,
                        labels=[f"{i*5}-{(i+1)*5}평" for i in range(10)]
                    ).value_counts().sort_index()
                    st.bar_chart(pyeong_counts)
        
        st.markdown("---")
        
        # 자치구별 통계 계산 (전체 데이터 기준)
        if "자치구" in df.columns:
            district_stats = []
            
            for district in sorted(df["자치구"].dropna().unique()):
                district_data = df[df["자치구"] == district]
                
                stats = {
                    "자치구": district,
                    "아파트 수": len(district_data)
                }
                
                # 평균 건축연도
                year_data = district_data["건축연도"].dropna()
                if len(year_data) > 0:
                    stats["평균 건축연도"] = f"{int(year_data.mean())}년"
                else:
                    stats["평균 건축연도"] = "N/A"
                
                # 평균 세대수
                household_data = district_data["세대수"].dropna()
                if len(household_data) > 0:
                    stats["평균 세대수"] = f"{int(household_data.mean())}세대"
                else:
                    stats["평균 세대수"] = "N/A"
                
                # 평균 평형 (세대당)
                if "세대당평균평형" in district_data.columns:
                    pyeong_data = district_data["세대당평균평형"].dropna()
                    if len(pyeong_data) > 0:
                        stats["평균 평형 (세대당)"] = f"{pyeong_data.mean():.1f}평"
                    else:
                        stats["평균 평형 (세대당)"] = "N/A"
                elif "평형" in district_data.columns:
                    pyeong_data = district_data["평형"].dropna()
                    if len(pyeong_data) > 0:
                        stats["평균 평형"] = f"{pyeong_data.mean():.1f}평"
                    else:
                        stats["평균 평형"] = "N/A"
                
                # 평균 주차대수
                if "주차대수" in district_data.columns:
                    parking_data = district_data["주차대수"].dropna()
                    if len(parking_data) > 0:
                        stats["평균 주차대수"] = f"{int(parking_data.mean())}대"
                    else:
                        stats["평균 주차대수"] = "N/A"
                
                # 평균 세대당 주차면수
                if "세대당주차면수" in district_data.columns:
                    parking_per_hh_data = district_data["세대당주차면수"].dropna()
                    if len(parking_per_hh_data) > 0:
                        stats["평균 세대당 주차면수"] = f"{parking_per_hh_data.mean():.2f}면"
                    else:
                        stats["평균 세대당 주차면수"] = "N/A"
                
                # 평균 지하철 거리
                distance_data = district_data["지하철역거리_km"].dropna()
                if len(distance_data) > 0:
                    stats["평균 지하철 거리"] = f"{distance_data.mean():.2f}km"
                else:
                    stats["평균 지하철 거리"] = "N/A"
                
                district_stats.append(stats)
            
            # 통계 테이블 생성
            if district_stats:
                stats_df = pd.DataFrame(district_stats)
                st.dataframe(
                    stats_df,
                    width="stretch",
                    height=910,
                    hide_index=True
                )
                
                # CSV 다운로드
                csv_stats = stats_df.to_csv(index=False, encoding='utf-8-sig')
                st.download_button(
                    label="📥 자치구별 통계 CSV 다운로드",
                    data=csv_stats,
                    file_name="district_statistics.csv",
                    mime="text/csv",
                    key="district_stats_download"
                )
else:
    st.warning("조건에 맞는 아파트가 없습니다. 필터를 조정해주세요.")

# 사이드바 하단
st.sidebar.markdown("---")
st.sidebar.markdown("### 데이터 새로고침")

# Streamlit secrets에서 비밀번호 확인 (TOML에서 숫자로 들어오면 문자열로 통일)
required_password = str(st.secrets.get("data_password", "1234")).strip()

# 비밀번호 입력
password_input = st.sidebar.text_input("비밀번호 입력", type="password", key="data_password_input")
password_ok = password_input and (password_input.strip() == required_password)

if st.sidebar.button("새 데이터 생성"):
    if password_ok:
        with st.sidebar:
            with st.status("🌐 서울 열린데이터광장 API에서 데이터 수집 중...", expanded=True) as status:
                try:
                    crawler = SeoulApartmentCrawler()
                    
                    # 먼저 작은 범위로 테스트
                    st.write("📡 API 연결 테스트 중... (1~100건)")
                    test_df = crawler.crawl_seoul_apartment_info(1, 100)
                    
                    if not test_df.empty:
                        st.write(f"API 테스트 성공! {len(test_df)}건 수집")
                        st.write("📥 전체 데이터 수집 시작 (1000개씩 배치)...")
                        
                        # 전체 데이터 수집 (5000개로 제한하여 시간 단축)
                        all_df = crawler.crawl_seoul_apartment_info_all(max_records=5000)
                        
                        if not all_df.empty:
                            st.write("🔄 데이터 처리 중...")
                            processed_df = crawler.process_seoul_apartment_info_data(all_df)
                            df_fresh = preprocess_apartment_df(processed_df)

                            # 세션에 저장 → 새로고침 시 load_data()가 이걸 최우선 사용 (Cloud에서도 동작)
                            st.session_state[SESSION_KEY_APARTMENT_DATA] = df_fresh

                            try:
                                crawler.save_to_csv(processed_df, "seoul_apartments_metadata.csv")
                            except Exception:
                                pass

                            load_data.clear()
                            status.update(label=f"✅ 데이터 수집 완료! (총 {len(df_fresh)}건)", state="complete")
                            st.success(f"실제 아파트 메타데이터 {len(df_fresh)}건이 수집되었습니다!")
                            st.info("🔄 화면이 새로고침되며 새로 수집된 데이터가 표시됩니다.")
                            st.rerun()
                        else:
                            status.update(label="❌ 데이터 수집 실패", state="error")
                            st.error("❌ 전체 데이터 수집에 실패했습니다. API 키를 확인해주세요.")
                    else:
                        status.update(label="❌ API 테스트 실패", state="error")
                        st.error("❌ API 연결에 실패했습니다. API 키를 확인해주세요.")
                        st.info("💡 API 키는 .env 파일 또는 환경변수에 SEOUL_DATA_API_KEY로 설정하세요.")
                        
                except Exception as e:
                    status.update(label="❌ 오류 발생", state="error")
                    st.error(f"❌ 오류가 발생했습니다: {str(e)}")
                    st.info("💡 API 키가 설정되어 있는지 확인하거나, 샘플 데이터를 사용하세요.")
    else:
        st.sidebar.error("❌ 비밀번호가 올바르지 않습니다.")

