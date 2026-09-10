"""인증된 사용자의 단지별 거래 비교 화면."""
import pandas as pd
import streamlit as st
from auth import is_tracker_logged_in, render_tracker_login_panel, logout_tracker


def common_areas(frames):
    sets = [set(df["전용면적_num"].dropna()) for df in frames]
    return sorted(set.intersection(*sets)) if sets else []


def filter_comparison(frame, start, end, area="전체", exclude_first=False):
    result = frame.loc[frame["계약년월"].between(start, end)]
    if area != "전체":
        result = result.loc[result["전용면적_num"] == area]
    if exclude_first:
        result = result.loc[result["층_num"] != 1]
    return result


def render_trade_compare(load_data, prepare, price_chart, volume_chart):
    if not is_tracker_logged_in():
        render_tracker_login_panel("단지 비교", "compare")
        return
    _, refresh_col, logout_col = st.columns([7, 2, 1])
    refresh = refresh_col.button("최신 데이터 불러오기", key="compare_refresh", use_container_width=True)
    if logout_col.button("로그아웃", key="compare_logout", use_container_width=True):
        logout_tracker()
        st.rerun()
    try:
        frame = prepare(load_data(force=refresh))
    except Exception:
        st.error("실거래 저장소를 읽지 못했습니다. 잠시 후 다시 불러와 주세요.")
        return
    if frame.empty:
        st.info("저장된 실거래가 없습니다. 크롤링 탭에서 수집해 주세요.")
        return
    identity = [c for c in ["구", "법정동", "아파트명", "지번"] if c in frame]
    if "아파트명" not in identity:
        st.info("단지명이 있는 데이터가 필요합니다.")
        return
    frame = frame.copy()
    frame["_complex"] = frame[identity].fillna("").astype(str).agg(" | ".join, axis=1)
    options = sorted(frame["_complex"].unique())
    preferred = next((x for x in options if all(s in x for s in ("성북구", "종암동", "종암에스케이"))), options[0])
    selected = st.multiselect("비교할 단지 (최대 3개)", options, default=[preferred], max_selections=3,
                             key="compare_complexes")
    if len(selected) < 2:
        st.info("단지를 2개 이상 선택하면 거래 내역을 나란히 비교합니다.")
        return
    frames = [frame.loc[frame["_complex"] == label] for label in selected]
    combined = pd.concat(frames)
    valid_dates = combined["계약일"].dropna()
    if valid_dates.empty:
        st.info("비교할 거래 날짜가 없습니다.")
        return
    months = pd.period_range(valid_dates.min(), valid_dates.max(), freq="M").astype(str).tolist()
    signature = "__".join(selected)
    if len(months) > 1:
        start, end = st.select_slider("비교 기간 (년월)", options=months,
                                      value=(months[max(0, len(months)-120)], months[-1]),
                                      key=f"compare_period_{signature}")
    else:
        start = end = months[0]
        st.caption(f"비교 기간: {start}")
    area_col, floor_col = st.columns([3, 1])
    shared = common_areas(frames)
    area = area_col.selectbox("공통 전용면적 (㎡)", ["전체"] + shared,
                              format_func=lambda x: x if x == "전체" else f"{x:.2f}㎡",
                              key=f"compare_area_{signature}_{shared}")
    exclude = floor_col.checkbox("1층 제외", key="compare_exclude_first")
    st.caption("선택한 모든 단지에 존재하는 같은 전용면적만 선택할 수 있습니다. 전체는 각 단지의 모든 면적을 포함합니다.")
    if not shared:
        st.caption("공통 전용면적이 없어 전체 면적으로 비교합니다.")
    views = [filter_comparison(df, start, end, area, exclude) for df in frames]
    years = list(range(int(start[:4]), int(end[:4]) + 1))
    annual = pd.DataFrame({"연도": [str(y) for y in years]})
    for label, df in zip(selected, views):
        counts = df["계약일"].dt.year.value_counts()
        annual[label] = [int(counts.get(y, 0)) for y in years]
    st.markdown("**연도별 거래 건수**")
    st.dataframe(annual, hide_index=True, use_container_width=True)
    st.caption("현재 필터와 저장된 거래 기준입니다. 0건에는 미수집 기간이 포함될 수 있습니다. 회색 배경은 서울 시장 반기 하락기입니다.")
    palette = sorted(combined["전용면적_num"].dropna().unique())
    prices = pd.concat(views)["거래금액_만원"].dropna() / 10000
    counts = [int(df.groupby("계약년월").size().max()) if not df.empty else 0 for df in views]
    columns = st.columns(len(selected))
    for i, (col, label, df) in enumerate(zip(columns, selected, views)):
        with col:
            st.markdown(f"**{label}**")
            st.caption(f"{start} ~ {end} · {len(df):,}건")
            fig = price_chart(df, "매매 실거래가", start, end)
            if not prices.empty:
                padding = max((prices.max() - prices.min()) * .08, .1)
                fig.update_yaxes(range=[max(0, prices.min()-padding), prices.max()+padding])
            st.plotly_chart(fig, use_container_width=True, key=f"compare_price_{i}", config={"displaylogo": False})
            volume = volume_chart(df, start, end, palette)
            volume.update_yaxes(range=[0, max(1, max(counts)) * 1.2])
            st.plotly_chart(volume, use_container_width=True, key=f"compare_volume_{i}", config={"displaylogo": False})
            st.caption("추세선: 이동 중앙값 · 파란 음영: 이동 20~80% 분위 구간")
            raw = df.sort_values("계약일", ascending=False).drop(columns=["_complex", "전용면적_num", "층_num", "계약년월"], errors="ignore")
            st.dataframe(raw, hide_index=True, use_container_width=True, height=360)
            st.download_button("원본 내역 CSV", raw.to_csv(index=False).encode("utf-8-sig"),
                               file_name=f"comparison_{i+1}.csv", mime="text/csv", key=f"compare_csv_{i}")
