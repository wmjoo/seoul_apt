"""
서울 아파트 검색 앱 (Streamlit)
"""
import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
from crawler import SeoulApartmentCrawler
from utils import extract_dong
import os


# 페이지 설정
st.set_page_config(
    page_title="서울 아파트 검색",
    page_icon="🏢",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 제목
st.title("🏢 서울 아파트 검색 시스템")
st.markdown("---")

# 데이터 로드 함수
@st.cache_data
def load_data():
    """데이터 로드 (캐싱)"""
    crawler = SeoulApartmentCrawler()
    
    # 우선순위: 메타데이터 > 일반 데이터 > 샘플 데이터
    if os.path.exists("seoul_apartments_metadata.csv"):
        df = crawler.load_from_csv("seoul_apartments_metadata.csv")
        st.toast(f"✅ 실제 아파트 메타데이터 로드 완료 ({len(df)}건)", icon="✅")
    elif os.path.exists("seoul_apartments.csv"):
        df = crawler.load_from_csv("seoul_apartments.csv")
        # 샘플 데이터인지 확인 (아파트명 컬럼이 없으면 샘플)
        if "아파트명" not in df.columns:
            st.toast("⚠️ 샘플 데이터를 사용 중입니다.", icon="⚠️")
    else:
        st.toast("데이터 파일이 없습니다. 샘플 데이터를 생성합니다...", icon="ℹ️")
        df = crawler.generate_sample_data(num_samples=500)
        crawler.save_to_csv(df, "seoul_apartments.csv")
    
    return df


# 데이터 로드
df = load_data()

# 동 정보 추가 (없으면 생성)
if "동" not in df.columns:
    df["동"] = df["주소"].apply(extract_dong)

# 사이드바 필터
st.sidebar.header("🔍 검색 필터")

# 자치구 필터
districts_list = df["자치구"].dropna().unique().tolist()
districts = ["전체"] + sorted([str(x) for x in districts_list if pd.notna(x) and str(x).strip()])
# 기본값을 동대문구로 설정 (동대문구가 있으면)
default_district = "동대문구" if "동대문구" in districts else "전체"
selected_district = st.sidebar.selectbox("자치구", districts, index=districts.index(default_district) if default_district in districts else 0)

# 동 필터 (자치구 선택 시 해당 자치구의 동만 표시)
if selected_district != "전체":
    district_df = df[df["자치구"] == selected_district]
    dong_list = district_df["동"].dropna().unique().tolist()
    dongs = ["전체"] + sorted([str(x) for x in dong_list if pd.notna(x) and str(x).strip()])
else:
    dong_list = df["동"].dropna().unique().tolist()
    dongs = ["전체"] + sorted([str(x) for x in dong_list if pd.notna(x) and str(x).strip()])

selected_dong = st.sidebar.selectbox("동", dongs)

# 필터링된 데이터 기준으로 슬라이더 범위 계산
if selected_district != "전체":
    filter_base = df[df["자치구"] == selected_district]
    if selected_dong != "전체":
        filter_base = filter_base[filter_base["동"] == selected_dong]
else:
    filter_base = df.copy()

# 건축연도 필터 (필터링된 데이터 기준)
year_data = filter_base["건축연도"].dropna()
if len(year_data) > 0:
    min_year = int(year_data.min())
    max_year = int(year_data.max())
    year_range = st.sidebar.slider(
        "건축연도 범위",
        min_value=min_year,
        max_value=max_year,
        value=(min_year, max_year),
        step=1
    )
else:
    year_range = (1900, 2025)

# 세대수 필터 (범주화: 0, 100, 300, 500, 1000, 1000>)
household_data = filter_base["세대수"].dropna()
if len(household_data) > 0:
    household_options = ["전체", "0", "100", "300", "500", "1000", "1000>"]
    selected_household = st.sidebar.selectbox("세대수", household_options)
    
    # 선택된 범주에 따라 필터링 범위 설정
    if selected_household == "전체":
        household_range = (0, float('inf'))
    elif selected_household == "0":
        household_range = (0, 0)
    elif selected_household == "100":
        household_range = (0, 100)
    elif selected_household == "300":
        household_range = (100, 300)
    elif selected_household == "500":
        household_range = (300, 500)
    elif selected_household == "1000":
        household_range = (500, 1000)
    else:  # 1000>
        household_range = (1000, float('inf'))
else:
    household_range = (0, float('inf'))

# 복도/계단식 필터
hallway_types_list = filter_base["복도계단식"].dropna().unique().tolist()
hallway_types = ["전체"] + sorted([str(x) for x in hallway_types_list if pd.notna(x)])
selected_hallway = st.sidebar.selectbox("복도/계단식", hallway_types)

# 평형 필터 제거 (사용자 요청)

# 지하철역 거리 필터 (범주화: 100m 미만, 100-250m, 250-500m, 500-750m, 750-1000m, 1000-1500, 1500-2000, 2000-3000, 3000>)
distance_data = filter_base["지하철역거리_km"].dropna()
if len(distance_data) > 0:
    distance_options = [
        "전체",
        "100m 미만",
        "100-250m",
        "250-500m",
        "500-750m",
        "750-1000m",
        "1000-1500m",
        "1500-2000m",
        "2000-3000m",
        "3000m 이상"
    ]
    selected_distance = st.sidebar.selectbox("지하철역 거리", distance_options)
    
    # 선택된 범주에 따라 필터링 범위 설정 (km 단위)
    if selected_distance == "전체":
        distance_range = (0.0, float('inf'))
    elif selected_distance == "100m 미만":
        distance_range = (0.0, 0.1)
    elif selected_distance == "100-250m":
        distance_range = (0.1, 0.25)
    elif selected_distance == "250-500m":
        distance_range = (0.25, 0.5)
    elif selected_distance == "500-750m":
        distance_range = (0.5, 0.75)
    elif selected_distance == "750-1000m":
        distance_range = (0.75, 1.0)
    elif selected_distance == "1000-1500m":
        distance_range = (1.0, 1.5)
    elif selected_distance == "1500-2000m":
        distance_range = (1.5, 2.0)
    elif selected_distance == "2000-3000m":
        distance_range = (2.0, 3.0)
    else:  # 3000m 이상
        distance_range = (3.0, float('inf'))
else:
    distance_range = (0.0, float('inf'))

# 지하철역 선택 필터 (자치구/동 선택 시 해당 지역 내 지하철역만 표시)
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
selected_subway = st.sidebar.selectbox("가장 가까운 지하철역", subway_stations)

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

# 세대수 필터 (NaN 값 처리) - 범주화된 필터 적용
if len(household_data) > 0:
    if household_range[1] == float('inf'):
        filtered_df = filtered_df[
            (filtered_df["세대수"].notna()) &
            (filtered_df["세대수"] >= household_range[0])
        ]
    else:
        filtered_df = filtered_df[
            (filtered_df["세대수"].notna()) &
            (filtered_df["세대수"] >= household_range[0]) &
            (filtered_df["세대수"] <= household_range[1])
        ]

if selected_hallway != "전체":
    filtered_df = filtered_df[filtered_df["복도계단식"] == selected_hallway]

# 평형 필터 제거 (사용자 요청)

# 지하철역 거리 필터 (NaN 값 처리)
if len(distance_data) > 0:
    if distance_range[1] == float('inf'):
        filtered_df = filtered_df[
            (filtered_df["지하철역거리_km"].notna()) &
            (filtered_df["지하철역거리_km"] >= distance_range[0])
        ]
    else:
        filtered_df = filtered_df[
            (filtered_df["지하철역거리_km"].notna()) &
            (filtered_df["지하철역거리_km"] >= distance_range[0]) &
            (filtered_df["지하철역거리_km"] <= distance_range[1])
        ]

if selected_subway != "전체":
    filtered_df = filtered_df[filtered_df["가장가까운지하철역"] == selected_subway]

# 결과 표시
st.header(f"📊 검색 결과: {len(filtered_df)}개")

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
        # 정렬 옵션
        sort_options = {
            "건축연도 (최신순)": "건축연도",
            "건축연도 (오래된순)": "건축연도",
            "세대수 (많은순)": "세대수",
            "세대당 평균 평형 (큰순)": "세대당평균평형",
            "세대당 평균 평형 (작은순)": "세대당평균평형",
            "주차대수 (많은순)": "주차대수",
            "세대당 주차면수 (많은순)": "세대당주차면수",
            "지하철 거리 (가까운순)": "지하철역거리_km"
        }
        sort_by = st.selectbox("정렬 기준", list(sort_options.keys()))
        ascending = "오래된순" in sort_by or "가까운순" in sort_by or "작은순" in sort_by
        
        sorted_df = filtered_df.sort_values(
            by=sort_options[sort_by],
            ascending=ascending
        )
        
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
        if "주소" in sorted_df.columns:
            display_columns.append("주소")
        if "건축연도" in sorted_df.columns:
            display_columns.append("건축연도")
        if "세대수" in sorted_df.columns:
            display_columns.append("세대수")
        if "복도계단식" in sorted_df.columns:
            display_columns.append("복도계단식")
        
        # 면적 정보 (세대당 평균만 표시)
        if "세대당평균평형" in sorted_df.columns:
            display_columns.append("세대당평균평형")
        
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
            "전용면적60㎡이하_세대수": "60㎡이하",
            "전용면적60_85㎡_세대수": "60~85㎡",
            "전용면적85_135㎡_세대수": "85~135㎡",
            "주차대수": "주차",
            "세대당주차면수": "세대당주차",
            "가장가까운지하철역": "지하철역",
            "지하철역거리_km": "지하철거리(km)"
        }
        
        # 컬럼명 변경
        display_df = display_df.rename(columns=column_mapping)
        
        # 건축연도 포맷팅 (콤마 제거, 정수로 표시)
        if "연도" in display_df.columns:
            display_df["연도"] = display_df["연도"].apply(
                lambda x: int(x) if pd.notna(x) else None
            )
        
        st.dataframe(
            display_df,
            use_container_width=True,
            height=400,
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
        st.subheader("아파트 위치 지도")
        
        # 지도 생성
        if len(filtered_df) > 0:
            center_lat = filtered_df["위도"].mean()
            center_lon = filtered_df["경도"].mean()
            
            m = folium.Map(
                location=[center_lat, center_lon],
                zoom_start=11,
                tiles="OpenStreetMap"
            )
            
            # 마커 추가
            for idx, row in filtered_df.iterrows():
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
            
            st_folium(m, width=1200, height=600)
        else:
            st.info("표시할 데이터가 없습니다.")
    
    with tab3:
        st.subheader("통계 분석")
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
        st.subheader("📊 자치구별 상세 통계")
        
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
                    use_container_width=True,
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

# Streamlit secrets에서 비밀번호 확인
if "data_password" in st.secrets:
    required_password = st.secrets["data_password"]
else:
    # 기본 비밀번호 (secrets에 없을 경우)
    required_password = "1234"

# 비밀번호 입력
password_input = st.sidebar.text_input("비밀번호 입력", type="password", key="data_password_input")

if st.sidebar.button("새 데이터 생성"):
    if password_input == required_password:
        with st.sidebar:
            with st.spinner("데이터 생성 중..."):
                crawler = SeoulApartmentCrawler()
                new_df = crawler.generate_sample_data(num_samples=500)
                crawler.save_to_csv(new_df, "seoul_apartments.csv")
                st.success("새 데이터가 생성되었습니다!")
                st.rerun()
    else:
        st.sidebar.error("❌ 비밀번호가 올바르지 않습니다.")

