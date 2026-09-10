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

from auth import (
    get_tracker_user,
    is_tracker_logged_in,
    logout_tracker,
    render_tracker_login_panel,
)
from crawler import SeoulApartmentCrawler
from config import SEOUL_DISTRICTS
from molit_trades import (
    collect_trades,
    current_ym,
    has_molit_api_key,
    load_trade_history,
    load_tracked_districts,
    months_back,
    save_tracked_districts,
    ym_to_date_span,
)
from sheets_store import is_sheets_configured, spreadsheet_url
from utils import extract_dong

# 새로 수집한 데이터를 세션에 넣어두는 키 (Cloud에서 파일 저장이 안 돼도 새로고침 반영)
SESSION_KEY_APARTMENT_DATA = "apartment_data"
SESSION_KEY_COLLECT_BANNER = "tracker_collect_banner"
SESSION_KEY_TRADES_CACHE = "cached_trades_df"
SESSION_KEY_BROWSE_QUERY = "browse_trade_query"
# 메인 아파트(실거래가) 단지명 유사도 매칭 임계값 (0~1). 0.75로 완화해 매칭률 상승
MAIN_APT_SIMILARITY_THRESHOLD = 0.75


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


def normalize_apt_strong(name):
    """단지명 강화 정규화(유사도 비교용): 1차/2차, 아파트, 단지, 괄호 안 내용 제거 후 공백 제거."""
    t = normalize_apt(name)
    t = re.sub(r"\s*[\(\（].*?[\)\）]\s*", "", t)
    t = re.sub(r"\s*[1-3]차\s*", "", t)
    t = re.sub(r"\s*아파트\s*", "", t, flags=re.IGNORECASE)
    t = re.sub(r"\s*단지\s*", "", t)
    t = re.sub(r"\s+", "", t)
    return t


def enrich_with_main_apt(df: pd.DataFrame, main_path: str) -> pd.DataFrame:
    """
    메인 아파트 CSV와 동 정규화 + 단지명 유사도 매칭으로 left join.
    - 1차: (자치구, norm_동) 일치 후보 중 단지명 유사도(강화 정규화) >= 임계값
    - 2차(fallback): 동 후보 없으면 자치구만으로 후보 확대 후 동일 유사도 매칭
    매칭되면 평수, 실거래가, 기준연월일 추가; 안 되면 공란.
    파일 없어도 컬럼은 추가해 테이블에 항상 표시.
    """
    df = df.copy()
    df["평수"] = None
    df["실거래가"] = None
    df["기준연월일"] = None
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
    main["norm_아파트명"] = main["아파트명"].apply(normalize_apt_strong)
    # (구, norm_동)별 후보 + 구별 후보(fallback)
    main_by_key = {}
    main_by_gu = {}
    for _, row in main.iterrows():
        key = (row["구"], row["norm_동"])
        if key not in main_by_key:
            main_by_key[key] = []
        main_by_key[key].append(row)
        g = row["구"]
        if g not in main_by_gu:
            main_by_gu[g] = []
        main_by_gu[g].append(row)

    if "자치구" not in df.columns or "동" not in df.columns or "아파트명" not in df.columns:
        return df
    for i in df.index:
        gu = df.at[i, "자치구"]
        dong = df.at[i, "동"]
        apt = df.at[i, "아파트명"]
        norm_dong = normalize_dong(dong)
        norm_apt = normalize_apt_strong(apt)
        candidates = main_by_key.get((gu, norm_dong), [])
        if not candidates:
            candidates = main_by_gu.get(gu, [])
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


def get_cached_trades(force: bool = False) -> pd.DataFrame:
    """실거래 이력을 세션에 캐시한다. (탭이 매 실행마다 그려져도 시트를 반복 조회하지 않음)"""
    if force or SESSION_KEY_TRADES_CACHE not in st.session_state:
        st.session_state[SESSION_KEY_TRADES_CACHE] = load_trade_history()
    cached = st.session_state[SESSION_KEY_TRADES_CACHE]
    if cached is None:
        return pd.DataFrame()
    return cached


def render_list_metrics(filtered_df: pd.DataFrame) -> None:
    """목록 탭 전용 평균 지표."""
    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        year_data = filtered_df["건축연도"].dropna()
        if len(year_data) > 0:
            st.metric("평균 건축연도", f"{int(year_data.mean())}년")
        else:
            st.metric("평균 건축연도", "N/A")
    with col2:
        household_data = filtered_df["세대수"].dropna()
        if len(household_data) > 0:
            st.metric("평균 세대수", f"{int(household_data.mean())}세대")
        else:
            st.metric("평균 세대수", "N/A")
    with col3:
        if "세대당평균평형" in filtered_df.columns:
            avg_pyeong_data = filtered_df["세대당평균평형"].dropna()
            if len(avg_pyeong_data) > 0:
                st.metric("평균 평형 (세대당)", f"{avg_pyeong_data.mean():.1f}평")
            elif "평형" in filtered_df.columns:
                pyeong_data = filtered_df["평형"].dropna()
                st.metric(
                    "평균 평형",
                    f"{pyeong_data.mean():.1f}평" if len(pyeong_data) > 0 else "N/A",
                )
            else:
                st.metric("평균 평형", "N/A")
        elif "평형" in filtered_df.columns:
            pyeong_data = filtered_df["평형"].dropna()
            st.metric(
                "평균 평형",
                f"{pyeong_data.mean():.1f}평" if len(pyeong_data) > 0 else "N/A",
            )
        else:
            st.metric("평균 평형", "N/A")
    with col4:
        if "주차대수" in filtered_df.columns:
            parking_data = filtered_df["주차대수"].dropna()
            parking_data = parking_data[parking_data >= 0]
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


def _unique_labels(series: pd.Series) -> list:
    return sorted({str(x).strip() for x in series.dropna() if str(x).strip()})


def _dong_col(df: pd.DataFrame) -> str:
    if "법정동" in df.columns:
        return "법정동"
    if "동" in df.columns:
        return "동"
    return ""


def _apt_col(df: pd.DataFrame) -> str:
    if "아파트명" in df.columns:
        return "아파트명"
    if "아파트" in df.columns:
        return "아파트"
    return ""


def _format_manwon(value) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    try:
        manwon = int(round(float(value)))
    except (TypeError, ValueError):
        return ""
    eok, rest = divmod(manwon, 10000)
    if eok and rest:
        return f"{eok}억 {rest:,}"
    if eok:
        return f"{eok}억"
    return f"{rest:,}만원"


def _prepare_browse_trades(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    if "계약일" in out.columns:
        out["계약일"] = pd.to_datetime(out["계약일"], errors="coerce")
    else:
        out["계약일"] = pd.NaT
    if out["계약일"].isna().any() and all(c in out.columns for c in ("년", "월", "일")):
        y = pd.to_numeric(out["년"], errors="coerce")
        m = pd.to_numeric(out["월"], errors="coerce")
        d = pd.to_numeric(out["일"], errors="coerce")
        parsed = pd.to_datetime({"year": y, "month": m, "day": d}, errors="coerce")
        out["계약일"] = out["계약일"].fillna(parsed)
    out["전용면적_num"] = (
        pd.to_numeric(out["전용면적"], errors="coerce").round(2)
        if "전용면적" in out.columns
        else pd.Series(pd.NA, index=out.index)
    )
    out["층_num"] = (
        pd.to_numeric(out["층"], errors="coerce") if "층" in out.columns else pd.Series(pd.NA, index=out.index)
    )
    if "거래금액_만원" in out.columns:
        out["거래금액_만원"] = pd.to_numeric(out["거래금액_만원"], errors="coerce")
    elif "거래금액" in out.columns:
        out["거래금액_만원"] = out["거래금액"].map(
            lambda x: int(re.sub(r"[^\d]", "", str(x))) if pd.notna(x) and re.sub(r"[^\d]", "", str(x)) else None
        )
    else:
        out["거래금액_만원"] = pd.NA
    out["계약년월"] = out["계약일"].dt.strftime("%Y-%m")
    out.loc[out["계약일"].isna(), "계약년월"] = ""
    if "해제여부" in out.columns:
        cancelled = out["해제여부"].astype(str).str.contains("해제", na=False)
        out = out.loc[~cancelled].copy()
    return out


def _apply_browse_query(df: pd.DataFrame, query: dict) -> pd.DataFrame:
    dong_col = _dong_col(df)
    apt_col = _apt_col(df)
    filtered = df
    gu = query.get("구") or "전체"
    dong = query.get("동") or "전체"
    apt = query.get("단지") or "전체"
    if gu != "전체" and "구" in filtered.columns:
        filtered = filtered[filtered["구"].astype(str).str.strip() == gu]
    if dong != "전체" and dong_col:
        filtered = filtered[filtered[dong_col].astype(str).str.strip() == dong]
    if apt != "전체" and apt_col:
        filtered = filtered[filtered[apt_col].astype(str).str.strip() == apt]
    return filtered


def _period_dtick(ym_start: str, ym_end: str) -> str:
    """기간 길이에 따라 x축 눈금: 10년 미만 3개월, 10년 6개월, 그 이상 1년."""
    start = pd.Timestamp(f"{ym_start}-01")
    end = pd.Timestamp(f"{ym_end}-01")
    months = (end.year - start.year) * 12 + (end.month - start.month) + 1
    if months > 132:
        return "M12"
    if months >= 120:
        return "M6"
    return "M3"


def _xaxis_period(ym_start: str, ym_end: str) -> dict:
    dtick = _period_dtick(ym_start, ym_end)
    return dict(
        showgrid=True,
        gridcolor="#f0f0f0",
        zeroline=False,
        tickformat="%y.%m",
        dtick=dtick,
        ticks="outside",
        range=[
            pd.Timestamp(f"{ym_start}-01"),
            pd.Timestamp(f"{ym_end}-01") + pd.offsets.MonthEnd(0),
        ],
    )


def _build_trade_chart(df: pd.DataFrame, title: str, ym_start: str = None, ym_end: str = None):
    import plotly.graph_objects as go

    chart_df = df.dropna(subset=["계약일", "거래금액_만원"]).sort_values("계약일")
    fig = go.Figure()
    if chart_df.empty:
        fig.update_layout(title=title, height=300, paper_bgcolor="white", plot_bgcolor="white")
        return fig

    price_eok = chart_df["거래금액_만원"].astype(float) / 10000.0
    dates = chart_df["계약일"]
    hover = [
        f"{d.strftime('%y.%m.%d')}<br>{_format_manwon(p)} / {int(f)}층 / {a:.2f}㎡"
        if pd.notna(f) and pd.notna(a)
        else f"{d.strftime('%y.%m.%d')}<br>{_format_manwon(p)}"
        for d, p, f, a in zip(dates, chart_df["거래금액_만원"], chart_df["층_num"], chart_df["전용면적_num"])
    ]

    if len(chart_df) >= 4:
        window = max(5, min(15, len(chart_df) // 6))
        mid = price_eok.rolling(window, center=True, min_periods=1).median()
        hi = price_eok.rolling(window, center=True, min_periods=1).quantile(0.8)
        lo = price_eok.rolling(window, center=True, min_periods=1).quantile(0.2)
        fig.add_trace(
            go.Scatter(
                x=dates,
                y=hi,
                mode="lines",
                line=dict(width=0),
                hoverinfo="skip",
                showlegend=False,
            )
        )
        fig.add_trace(
            go.Scatter(
                x=dates,
                y=lo,
                mode="lines",
                line=dict(width=0, color="#90caf9"),
                fill="tonexty",
                fillcolor="rgba(33, 150, 243, 0.16)",
                hoverinfo="skip",
                name="추세 구간",
            )
        )
        fig.add_trace(
            go.Scatter(
                x=dates,
                y=mid,
                mode="lines",
                line=dict(color="#1976d2", width=2.4, dash="solid"),
                name="추세",
            )
        )

    fig.add_trace(
        go.Scatter(
            x=dates,
            y=price_eok,
            mode="markers",
            marker=dict(color="#e53935", size=9, opacity=0.88, line=dict(width=0.6, color="white")),
            name="실거래가",
            text=hover,
            hovertemplate="%{text}<extra></extra>",
        )
    )
    xaxis = (
        _xaxis_period(ym_start, ym_end)
        if ym_start and ym_end
        else dict(showgrid=True, gridcolor="#f0f0f0", zeroline=False, tickformat="%y.%m")
    )
    fig.update_layout(
        title=dict(text=title, font=dict(size=16)),
        height=300,
        margin=dict(l=48, r=16, t=48, b=36),
        paper_bgcolor="white",
        plot_bgcolor="white",
        hovermode="closest",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0, bgcolor="rgba(0,0,0,0)"),
        xaxis=xaxis,
        yaxis=dict(
            title="",
            ticksuffix="억",
            showgrid=True,
            gridcolor="#eeeeee",
            zeroline=False,
        ),
    )
    return fig


_VOLUME_PALETTE = [
    "#42a5f5",
    "#66bb6a",
    "#ffa726",
    "#ab47bc",
    "#26c6da",
    "#ef5350",
    "#8d6e63",
    "#d4e157",
    "#5c6bc0",
    "#ec407a",
    "#78909c",
    "#ffca28",
]


def _area_label(value) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return "면적미상"
    try:
        return f"{float(value):.2f}㎡"
    except (TypeError, ValueError):
        return "면적미상"


def _build_volume_chart(df: pd.DataFrame, ym_start: str, ym_end: str, palette_areas: list):
    """월별 거래 건수. 전용면적별로 스택하고, 면적 필터와 동기화한다."""
    import plotly.graph_objects as go

    months = pd.date_range(start=f"{ym_start}-01", end=f"{ym_end}-01", freq="MS")
    fig = go.Figure()
    work = df.copy()
    work["면적"] = work["전용면적_num"].map(_area_label)
    work["월"] = pd.to_datetime(work["계약년월"].astype(str) + "-01", errors="coerce")
    work = work.dropna(subset=["월"])

    palette_labels = [_area_label(a) for a in palette_areas]
    if (work["면적"] == "면적미상").any() and "면적미상" not in palette_labels:
        palette_labels.append("면적미상")
    color_map = {
        label: _VOLUME_PALETTE[i % len(_VOLUME_PALETTE)] for i, label in enumerate(palette_labels)
    }
    present = [lab for lab in palette_labels if lab in set(work["면적"])]
    if not present:
        present = sorted(work["면적"].dropna().unique().tolist())

    for lab in present:
        counts = work.loc[work["면적"] == lab].groupby("월").size()
        counts = counts.reindex(months, fill_value=0)
        fig.add_trace(
            go.Bar(
                x=counts.index,
                y=counts.values,
                name=lab,
                marker_color=color_map.get(lab, "#90a4ae"),
                hovertemplate=f"{lab}<br>%{{x|%y.%m}}<br>%{{y}}건<extra></extra>",
            )
        )

    totals = work.groupby("월").size().reindex(months, fill_value=0)
    fig.add_trace(
        go.Scatter(
            x=totals.index,
            y=totals.values,
            mode="text",
            text=[str(int(v)) if v else "" for v in totals.values],
            textposition="top center",
            textfont=dict(size=10, color="#424242"),
            showlegend=False,
            hoverinfo="skip",
        )
    )
    ymax = float(totals.max()) if len(totals) else 0.0
    xaxis = _xaxis_period(ym_start, ym_end)
    xaxis["showgrid"] = False
    fig.update_layout(
        title=dict(text="월별 거래 건수", font=dict(size=16)),
        barmode="stack",
        height=280,
        margin=dict(l=48, r=16, t=64, b=36),
        paper_bgcolor="white",
        plot_bgcolor="white",
        bargap=0.18,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0, bgcolor="rgba(0,0,0,0)"),
        xaxis=xaxis,
        yaxis=dict(
            title="건수",
            showgrid=True,
            gridcolor="#eeeeee",
            rangemode="tozero",
            zeroline=False,
            range=[0, ymax * 1.22 if ymax else 1],
        ),
    )
    return fig


def render_trade_browse() -> None:
    """로그인 없이 실거래 내역을 조회한다."""
    st.subheader("실거래가 조회")
    refresh = st.button("최신 데이터 불러오기", key="browse_refresh")
    try:
        trades_df = get_cached_trades(force=refresh)
    except Exception:
        st.error("실거래 저장소를 읽지 못했습니다. 잠시 후 최신 데이터 불러오기를 눌러주세요.")
        return
    if trades_df.empty:
        st.info("저장된 실거래가 없습니다. 실거래가 크롤링 탭에서 수집하면 여기에 표시됩니다.")
        return

    trades_df = _prepare_browse_trades(trades_df)
    dong_col = _dong_col(trades_df)
    apt_col = _apt_col(trades_df)
    gu_values = _unique_labels(trades_df["구"]) if "구" in trades_df.columns else []
    gu_options = ["전체"] + gu_values
    default_gu = "동대문구" if "동대문구" in gu_values else (gu_values[0] if gu_values else "전체")

    gcol, dcol, acol, bcol = st.columns([2.3, 2.3, 3.1, 0.9])
    with gcol:
        selected_gu = st.selectbox(
            "구",
            gu_options,
            index=gu_options.index(default_gu) if default_gu in gu_options else 0,
            key="browse_gu_filter",
        )
    gu_df = trades_df if selected_gu == "전체" or "구" not in trades_df.columns else trades_df[
        trades_df["구"].astype(str).str.strip() == selected_gu
    ]
    dong_options = ["전체"]
    if dong_col:
        dong_options += _unique_labels(gu_df[dong_col])
    with dcol:
        selected_dong = st.selectbox(
            "동",
            dong_options,
            index=0,
            key=f"browse_dong_filter_{selected_gu}",
        )
    dong_df = gu_df if selected_dong == "전체" or not dong_col else gu_df[
        gu_df[dong_col].astype(str).str.strip() == selected_dong
    ]
    apt_options = ["전체"]
    if apt_col:
        apt_options += _unique_labels(dong_df[apt_col])
    with acol:
        selected_apt = st.selectbox(
            "단지명",
            apt_options,
            index=0,
            key=f"browse_apt_filter_{selected_gu}_{selected_dong}",
        )
    with bcol:
        st.markdown("<div style='height:1.7rem'></div>", unsafe_allow_html=True)
        searched = st.button("검색", width="stretch", key="browse_search_btn")

    if searched:
        st.session_state[SESSION_KEY_BROWSE_QUERY] = {
            "구": selected_gu,
            "동": selected_dong,
            "단지": selected_apt,
        }
    query = st.session_state.get(SESSION_KEY_BROWSE_QUERY)
    if query and query != {"구": selected_gu, "동": selected_dong, "단지": selected_apt}:
        st.info("검색 조건이 변경되었습니다. 검색 버튼을 눌러 결과에 적용하세요.")
    if not query:
        st.info("구·동·단지를 선택한 뒤 검색을 누르세요.")
        return

    result_df = _apply_browse_query(trades_df, query)
    if result_df.empty:
        st.warning("조건에 맞는 실거래가 없습니다.")
        return

    ym_options = sorted(x for x in result_df["계약년월"].dropna().unique() if x)
    if not ym_options:
        st.warning("계약일 정보가 없어 기간을 선택할 수 없습니다.")
        return

    ym_options = pd.period_range(ym_options[0], ym_options[-1], freq="M").astype(str).tolist()
    default_end = ym_options[-1]
    cut = (pd.Timestamp(default_end + "-01") - pd.DateOffset(months=119)).strftime("%Y-%m")
    default_start = next((x for x in ym_options if x >= cut), ym_options[0])
    query_key = f"{query.get('구')}_{query.get('동')}_{query.get('단지')}"
    if len(ym_options) == 1:
        ym_start = ym_end = ym_options[0]
        st.caption(f"기간 {ym_start}")
    else:
        ym_start, ym_end = st.select_slider(
            "기간",
            options=ym_options,
            value=(default_start, default_end),
            key=f"browse_ym_range_{query_key}_10y",
        )

    period_df = result_df[(result_df["계약년월"] >= ym_start) & (result_df["계약년월"] <= ym_end)]
    areas = sorted({float(a) for a in result_df["전용면적_num"].dropna().unique()})
    area_labels = ["전체"] + [f"{a:.2f}㎡" for a in areas]
    area_default = "전체"
    if areas:
        mode_area = result_df["전용면적_num"].mode()
        if len(mode_area) > 0:
            area_default = f"{float(mode_area.iloc[0]):.2f}㎡"
    fcol, ccol = st.columns([2, 3])
    with fcol:
        selected_area = st.selectbox(
            "전용면적",
            area_labels,
            index=area_labels.index(area_default) if area_default in area_labels else 0,
            key=f"browse_area_{query_key}",
        )
    with ccol:
        st.markdown("<div style='height:1.7rem'></div>", unsafe_allow_html=True)
        exclude_first = st.checkbox("1층 제외", value=False, key=f"browse_exclude_1f_{query_key}")

    view_df = period_df
    if selected_area != "전체":
        area_num = float(selected_area.replace("㎡", ""))
        view_df = view_df[view_df["전용면적_num"] == area_num]
    if exclude_first:
        view_df = view_df[view_df["층_num"].fillna(-999) != 1]

    apt_title = query.get("단지") if query.get("단지") not in (None, "전체") else "선택한 조건"
    st.caption(f"{query.get('구')} {query.get('동')} {query.get('단지')} · {len(view_df):,}건")
    if view_df.empty:
        st.info("필터에 맞는 실거래가 없습니다. 기간이나 전용면적을 바꿔보세요.")
        return

    if query.get("단지") in (None, "전체"):
        st.caption("단지를 선택해 검색하면 시세 점·추세 차트가 표시됩니다.")
    else:
        st.plotly_chart(
            _build_trade_chart(view_df, f"{apt_title} 매매 실거래가", ym_start, ym_end),
            use_container_width=True,
            config={"scrollZoom": True, "displaylogo": False},
        )
    st.plotly_chart(
        _build_volume_chart(view_df, ym_start, ym_end, areas),
        use_container_width=True,
        config={"scrollZoom": True, "displaylogo": False},
    )

    show_cols = [
        c
        for c in ["계약일", "구", "법정동", "아파트명", "전용면적", "평", "층", "거래금액_만원", "거래유형"]
        if c in view_df.columns
    ]
    table_df = view_df.sort_values("계약일", ascending=False)[show_cols].copy()
    if "계약일" in table_df.columns:
        table_df["계약일"] = pd.to_datetime(table_df["계약일"]).dt.strftime("%Y-%m-%d")
    if "거래금액_만원" in table_df.columns:
        table_df["거래금액"] = table_df["거래금액_만원"].map(_format_manwon)
        table_df = table_df.drop(columns=["거래금액_만원"])
    st.dataframe(table_df, width="stretch", hide_index=True, height=420)
    st.download_button(
        label="📥 실거래 내역 CSV 다운로드",
        data=table_df.to_csv(index=False, encoding="utf-8-sig"),
        file_name="apt_trades_filtered.csv",
        mime="text/csv",
        key="browse_trades_download",
    )


def render_tracker_tab(apartment_df: pd.DataFrame = None) -> None:
    """실거래가 크롤링 탭: 비로그인은 로그인 폼, 로그인은 수집 화면."""
    if not is_tracker_logged_in():
        render_tracker_login_panel()
        return

    top, logout_col = st.columns([4, 1])
    with top:
        st.caption(f"{get_tracker_user()} 님으로 로그인됨")
    with logout_col:
        if st.button("로그아웃", width="stretch", key="tracker_logout"):
            logout_tracker()
            st.rerun()
    render_trade_tracker(apartment_df)


def render_trade_tracker(apartment_df: pd.DataFrame = None) -> None:
    """로그인 사용자 전용 실거래 수집."""
    st.subheader("실거래가 크롤링")
    if is_sheets_configured():
        st.caption("선택한 구의 매매 실거래는 비공개 Google 시트의 `trades` 탭에 저장됩니다.")
        sheet_url = spreadsheet_url()
        if sheet_url:
            st.link_button("Google 시트 열기", sheet_url)
    else:
        st.warning(
            "Google 시트가 아직 연결되지 않았습니다. "
            "`secrets.toml`에 `[gcp_service_account]`와 `sheets.spreadsheet_id`를 넣으면 "
            "비공개 시트로 저장됩니다. 지금은 로컬 CSV로 동작합니다."
        )

    if has_molit_api_key():
        st.caption("국토부 API 키가 연결되어 있습니다.")
    else:
        st.warning("`.streamlit/secrets.toml`의 `PUBLIC_DATA_API_KEY`를 확인하세요.")

    try:
        tracked = load_tracked_districts()
    except Exception:
        st.error("추적 구를 불러오지 못했습니다. 저장소 연결을 확인해주세요.")
        return
    st.markdown("#### 추적 구")
    if not tracked:
        st.info("아래에서 구를 추가한 뒤 수집을 실행하세요. 선택한 구의 거래가 전부 저장됩니다.")
    else:
        remaining = st.multiselect(
            "추적 구",
            options=tracked,
            default=tracked,
            key="tracker_district_chips_" + "_".join(tracked),
            label_visibility="collapsed",
            placeholder="추적 중인 구가 없습니다.",
        )
        if list(remaining) != list(tracked):
            save_tracked_districts([g for g in tracked if g in remaining])
            st.rerun()

    addable = [g for g in SEOUL_DISTRICTS if g not in tracked]
    add_col, add_btn = st.columns([3, 1])
    with add_col:
        add_gu = st.selectbox("구 추가", addable, key="tracker_add_gu") if addable else None
    with add_btn:
        st.write("")
        if st.button("추가", width="stretch", disabled=not add_gu, key="tracker_add_btn") and add_gu:
            save_tracked_districts(tracked + [add_gu])
            st.rerun()

    st.markdown("#### 수집")
    can_collect = has_molit_api_key() and bool(tracked)

    def _run_collect(start_ym: str, skip_complete_months: bool) -> None:
        bar = st.progress(0, text="수집 시작")
        last_toast_year = None

        def on_progress(done, total, msg):
            nonlocal last_toast_year
            frac = (done / total) if total else 0.0
            bar.progress(min(1.0, frac), text=f"{msg} ({done}/{total})")
            year = None
            parts = msg.split()
            if len(parts) >= 2 and "." in parts[1]:
                year = parts[1].split(".")[0]
            should_toast = done == 0 or done == total or (year and year != last_toast_year)
            if should_toast:
                st.toast(f"{msg} ({done}/{total})")
                last_toast_year = year

        existing = get_cached_trades()
        before = 0 if existing.empty else len(existing)
        end_ym = current_ym()
        merged = collect_trades(
            tracked,
            start_ym=start_ym,
            end_ym=end_ym,
            on_progress=on_progress,
            skip_complete_months=skip_complete_months,
        )
        added = max(0, len(merged) - before)
        start_d, end_d = ym_to_date_span(start_ym, end_ym)
        st.session_state[SESSION_KEY_TRADES_CACHE] = merged
        st.session_state[SESSION_KEY_COLLECT_BANNER] = {
            "start": start_d,
            "end": end_d,
            "count": added,
        }
        bar.progress(1.0, text=f"수집 완료 ({added}건)")
        st.toast(f"[{start_d}~{end_d}] {added:,}건 수집완료")
        st.rerun()

    c_all, c_3y, c_1y, c_6m, c_3m = st.columns(5)
    with c_all:
        if st.button("전체", width="stretch", disabled=not can_collect, key="tracker_collect_all"):
            try:
                _run_collect("200601", skip_complete_months=True)
            except Exception as exc:
                st.error(str(exc))
    with c_3y:
        if st.button("최근 3년", width="stretch", disabled=not can_collect, key="tracker_collect_3y"):
            try:
                _run_collect(months_back(36), skip_complete_months=True)
            except Exception as exc:
                st.error(str(exc))
    with c_1y:
        if st.button("최근 1년", width="stretch", disabled=not can_collect, key="tracker_collect_1y"):
            try:
                _run_collect(months_back(12), skip_complete_months=True)
            except Exception as exc:
                st.error(str(exc))
    with c_6m:
        if st.button("최근 6개월", width="stretch", disabled=not can_collect, key="tracker_collect_6m"):
            try:
                _run_collect(months_back(6), skip_complete_months=False)
            except Exception as exc:
                st.error(str(exc))
    with c_3m:
        if st.button("최근 3개월", width="stretch", disabled=not can_collect, key="tracker_collect_3m"):
            try:
                _run_collect(months_back(3), skip_complete_months=False)
            except Exception as exc:
                st.error(str(exc))
    if can_collect:
        st.caption(
            "전체·최근 3년·최근 1년은 시트에 해당 구의 해당 월 1일~말일 데이터가 있으면 건너뜁니다. "
            "최근 6개월·최근 3개월은 항상 다시 수집합니다."
        )
    if not can_collect:
        if not has_molit_api_key():
            st.caption("국토부 API 키가 연결되면 수집할 수 있습니다.")
        elif not tracked:
            st.caption("구를 추가하면 수집 버튼이 활성화됩니다.")

    st.markdown("#### 실거래 내역")
    banner = st.session_state.get(SESSION_KEY_COLLECT_BANNER)
    if banner:
        start_d = banner.get("start", "")
        end_d = banner.get("end", "")
        count = int(banner.get("count", 0) or 0)
        st.text(f"[{start_d}~{end_d}] {count:,}건 수집완료")
    else:
        st.caption("수집이 끝나면 기간과 건수가 여기에 표시됩니다.")


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

# 데이터 로드 메시지 표시 (toast 비활성화)
# if data_type == "metadata":
#     st.toast(f"실제 아파트 메타데이터 로드 완료 ({data_count}건)", icon="✅")
# elif data_type == "sample":
#     st.toast("샘플 데이터를 사용 중입니다.", icon="⚠️")
# elif data_type == "generated":
#     st.toast("데이터 파일이 없습니다. 샘플 데이터를 생성합니다...", icon="ℹ️")

# 동 정보 추가 (없으면 생성)
if "동" not in df.columns:
    df["동"] = df["주소"].apply(extract_dong)

# 메인 아파트(실거래가) CSV와 동 정규화 + 단지명 유사도 매칭으로 평수/실거래가/기준연월일 추가
_main_apt_file = "seoul_disrict_main_apt.csv"
if not os.path.exists(_main_apt_file):
    try:
        _alt = os.path.join(os.path.dirname(os.path.abspath(__file__)), _main_apt_file)
        if os.path.exists(_alt):
            _main_apt_file = _alt
    except NameError:
        pass
df = enrich_with_main_apt(df, _main_apt_file)

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

MAIN_TABS = ["📋 목록", "🗺️ 지도", "📈 통계", "🔎 실거래가 조회", "🔒 실거래가 크롤링"]

if len(filtered_df) > 0:
    tab1, tab2, tab3, tab4, tab5 = st.tabs(MAIN_TABS)

    with tab1:
        render_list_metrics(filtered_df)
        st.markdown("---")
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

    with tab4:
        render_trade_browse()
    with tab5:
        render_tracker_tab(df)
else:
    st.warning("조건에 맞는 아파트가 없습니다. 필터를 조정해주세요.")
    tab1, tab2, tab3, tab4, tab5 = st.tabs(MAIN_TABS)
    with tab1:
        st.info("검색 결과가 없습니다. 필터를 조정해주세요.")
    with tab2:
        st.info("검색 결과가 없습니다. 필터를 조정해주세요.")
    with tab3:
        st.info("검색 결과가 없습니다. 필터를 조정해주세요.")
    with tab4:
        render_trade_browse()
    with tab5:
        render_tracker_tab(df)

# 사이드바 하단
st.sidebar.markdown("---")
st.sidebar.markdown("### 데이터 새로고침")

# Streamlit secrets에서 비밀번호 확인
# Cloud Secrets: [secrets] 섹션 사용 시 → st.secrets["secrets"]["data_password"]
#               섹션 없이 data_password = "xxx" → st.secrets["data_password"]
def _get_data_password():
    try:
        if not getattr(st, "secrets", None):
            return ""
        raw = None
        try:
            raw = st.secrets["secrets"]["data_password"]
        except (KeyError, TypeError, AttributeError):
            try:
                raw = st.secrets["data_password"]
            except (KeyError, TypeError):
                raw = getattr(st.secrets, "data_password", None)
        if raw is None:
            return ""
        return str(raw).strip()
    except Exception:
        return ""

required_password = _get_data_password()
_col_pw, _col_btn = st.sidebar.columns([1, 1])
with _col_pw:
    password_input = st.text_input("비밀번호 입력", type="password", key="data_password_input")
input_stripped = (password_input or "").strip()
required_stripped = (required_password or "").strip()
password_ok = bool(required_stripped and input_stripped == required_stripped)

# 비밀번호가 맞을 때만 오른쪽 영역에 '새 데이터 생성' 버튼 표시
if password_ok:
    with _col_btn:
        if st.button("새 데이터 생성", width="stretch"):
            with st.status("🌐 서울 열린데이터광장 API에서 데이터 수집 중...", expanded=True) as status:
                try:
                    crawler = SeoulApartmentCrawler()
                    
                    st.write("📡 API 연결 테스트 중... (1~100건)")
                    test_df = crawler.crawl_seoul_apartment_info(1, 100)
                    
                    if not test_df.empty:
                        st.write(f"API 테스트 성공! {len(test_df)}건 수집")
                        st.write("📥 전체 데이터 수집 시작 (1000개씩 배치)...")
                        
                        all_df = crawler.crawl_seoul_apartment_info_all(max_records=5000)
                        
                        if not all_df.empty:
                            st.write("🔄 데이터 처리 중...")
                            processed_df = crawler.process_seoul_apartment_info_data(all_df)
                            df_fresh = preprocess_apartment_df(processed_df)

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
    with _col_btn:
        st.caption("비밀번호가 일치하면 버튼이 표시됩니다.")

