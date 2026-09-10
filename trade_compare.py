"""인증된 사용자의 단지별 거래 비교 화면."""
import pandas as pd
import streamlit as st
from trade_controls import period_control, date_bounds, area_values, grouped_chart_frame
from trade_metadata import name_key
from market_cycles import shade_downturns
from auth import is_tracker_logged_in, render_tracker_login_panel, logout_tracker


def common_areas(frames):
    sets = [set(area_values(df, True).dropna().astype(int)) for df in frames]
    return sorted(set.intersection(*sets)) if sets else []


def preferred_overlay_area(frames, shared):
    if not shared:
        return None
    values = pd.concat([area_values(df, True) for df in frames], ignore_index=True)
    ranked = values[values.isin(shared)].value_counts()
    return int(ranked.index[0]) if len(ranked) else int(shared[0])


def overlay_colors(count):
    palettes = {
        1: ["#2563EB"],
        2: ["#0072B2", "#D55E00"],
        3: ["#0072B2", "#D55E00", "#009E73"],
        4: ["#0072B2", "#D55E00", "#009E73", "#CC79A7"],
    }
    fallback = ["#0072B2", "#D55E00", "#009E73", "#CC79A7", "#E69F00", "#56B4E9"]
    return palettes.get(count, fallback[:count])


def filter_comparison(frame, start, end, area="전체", exclude_first=False):
    left, right = date_bounds(start, end)
    result = frame.loc[pd.to_datetime(frame["계약일"]).between(left, right + pd.Timedelta(days=1), inclusive="left")]
    if area != "전체":
        result = result.loc[area_values(result, True) == area]
    if exclude_first:
        result = result.loc[result["층_num"] != 1]
    return result


def render_trade_compare(load_data, prepare, price_chart, volume_chart, apartments=None):
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
    labels = complex_labels(frame, apartments)
    options = sorted(frame["_complex"].unique(), key=labels.get)
    preferred_complex = next((x for x in options if all(s in x for s in ("성북구", "종암동", "종암에스케이"))), options[0])
    selected = st.multiselect("비교할 단지 (최대 3개)", options, default=[preferred_complex], max_selections=3,
                             key="compare_complexes", format_func=labels.get)
    if len(selected) < 2:
        st.info("단지를 2개 이상 선택하면 거래 내역을 나란히 비교합니다.")
        return
    frames = [frame.loc[frame["_complex"] == label] for label in selected]
    combined = pd.concat(frames)
    valid_dates = combined["계약일"].dropna()
    if valid_dates.empty:
        st.info("비교할 거래 날짜가 없습니다.")
        return
    signature = "__".join(selected)
    start, end = period_control(f"compare_period_{signature}")
    area_col, floor_col = st.columns([3, 1])
    shared = common_areas(frames)
    area = area_col.selectbox("공통 전용면적 (개별 차트·건수)", ["전체"] + shared,
                              format_func=lambda x: x if x == "전체" else f"{int(x)}㎡",
                              key=f"compare_area_{signature}_{shared}")
    exclude = floor_col.checkbox("1층 제외", key="compare_exclude_first")
    st.caption("소수점을 버린 정수 면적(59·84·114㎡)으로 묶어 공통 면적을 비교합니다. 전체는 각 단지의 모든 면적을 포함합니다.")
    if not shared:
        st.caption("공통 전용면적이 없어 전체 면적으로 비교합니다.")
    views = [filter_comparison(df, start, end, area, exclude) for df in frames]
    named = [labels[x] for x in selected]
    st.markdown("**반기별 거래 건수**")
    st.dataframe(half_year_activity(views, named, start, end),
                 hide_index=True, use_container_width=True)
    st.caption("현재 필터와 저장된 거래 기준입니다. 0건에는 미수집 기간이 포함될 수 있습니다.")
    st.markdown("**단지별 매매 실거래가 비교**")
    if shared:
        overlay_default = preferred_overlay_area(frames, shared)
        overlay_area = st.selectbox("통합 비교 차트 전용면적 (㎡)", shared,
                                    index=shared.index(overlay_default) if overlay_default in shared else 0,
                                    format_func=lambda x: f"{int(x)}㎡",
                                    key=f"overlay_area_{signature}_{shared}")
        overlay_views = [filter_comparison(df, start, end, overlay_area, exclude) for df in frames]
        st.plotly_chart(build_overlay(overlay_views, named, start, end, overlay_area),
                        use_container_width=True, key="compare_overlay",
                        config={"displaylogo": False, "scrollZoom": True})
        st.caption("통합 차트는 위 전용면적만 적용합니다. 선: 단지별 이동 중앙값 · 점: 실제 거래 · 회색 배경: 서울 시장 반기 하락기")
    else:
        st.info("공통 정수 면적이 없어 동일 면적 통합 차트를 표시할 수 없습니다.")
    palette = sorted(area_values(combined, True).dropna().unique())
    prices = pd.concat(views)["거래금액_만원"].dropna() / 10000
    counts = [int(df.groupby("계약년월").size().max()) if not df.empty else 0 for df in views]
    columns = st.columns(len(selected))
    for i, (col, label, df) in enumerate(zip(columns, selected, views)):
        with col:
            st.markdown(f"**{labels[label]}**")
            st.caption(f"{start} ~ {end} · {len(df):,}건")
            fig = price_chart(df, "매매 실거래가", start, end)
            if not prices.empty:
                padding = max((prices.max() - prices.min()) * .08, .1)
                fig.update_yaxes(range=[max(0, prices.min()-padding), prices.max()+padding])
            st.plotly_chart(fig, use_container_width=True, key=f"compare_price_{i}", config={"displaylogo": False})
            volume = volume_chart(grouped_chart_frame(df), start, end, palette)
            volume.update_yaxes(range=[0, max(1, max(counts)) * 1.2])
            st.plotly_chart(volume, use_container_width=True, key=f"compare_volume_{i}", config={"displaylogo": False})
            st.caption("추세선: 이동 중앙값 · 파란 음영: 이동 20~80% 분위 구간")
            raw = df.sort_values("계약일", ascending=False).drop(columns=["_complex", "전용면적_num", "층_num", "계약년월"], errors="ignore")
            st.dataframe(raw, hide_index=True, use_container_width=True, height=360)
            st.download_button("원본 내역 CSV", raw.to_csv(index=False).encode("utf-8-sig"),
                               file_name=f"comparison_{i+1}.csv", mime="text/csv", key=f"compare_csv_{i}")


def complex_labels(frame, apartments=None):
    """표시 라벨과 단지 식별 키를 분리하며, 모호한 메타데이터는 추정하지 않는다."""
    household_lookup = {}
    if apartments is not None and not apartments.empty:
        for _, row in apartments.iterrows():
            key = (name_key(row.get("아파트명", "")), str(row.get("자치구", "")).strip(), str(row.get("동", "")).strip())
            count = pd.to_numeric(row.get("세대수"), errors="coerce")
            if pd.notna(count) and count > 0:
                household_lookup.setdefault(key, set()).add(int(count))
    labels = {}
    first_rows = frame.drop_duplicates("_complex")
    for _, row in first_rows.iterrows():
        name, gu, dong = [str(row.get(c, "")).strip() for c in ("아파트명", "구", "법정동")]
        counts = household_lookup.get((name_key(name), gu, dong), set())
        own_count = pd.to_numeric(row.get("세대수"), errors="coerce")
        if not counts and pd.notna(own_count) and own_count > 0:
            counts = {int(own_count)}
        household = f"{next(iter(counts)):,}세대" if len(counts) == 1 else "세대수 미상"
        labels[row["_complex"]] = f"{name}({gu} {dong}) [{household}]"
    # 이름/동이 같고 지번이 다른 경우에만 식별에 필요한 지번을 덧붙인다.
    duplicate_labels = pd.Series(list(labels.values())).value_counts()
    for _, row in first_rows.iterrows():
        key = row["_complex"]
        if duplicate_labels[labels[key]] > 1:
            labels[key] += f" · {row.get('지번', '')}"
    return labels


def half_year_activity(frames, labels, start, end):
    periods = list(dict.fromkeys((m.year, 1 if m.month <= 6 else 2)
                                for m in pd.period_range(start, end, freq="M")))
    result = pd.DataFrame({"반기": [f"{year} {'상반기' if half == 1 else '하반기'}" for year, half in periods]})
    for label, frame in zip(labels, frames):
        dates = pd.to_datetime(frame["계약일"])
        counts = dates.map(lambda d: (d.year, 1 if d.month <= 6 else 2)).value_counts()
        result[label] = [int(counts.get(period, 0)) for period in periods]
    return result


def build_overlay(frames, labels, start, end, area=None):
    import plotly.graph_objects as go
    colors = overlay_colors(len(frames))
    symbols = ["circle", "diamond", "square", "x", "triangle-up"]
    fig = go.Figure()
    for index, (frame, label) in enumerate(zip(frames, labels)):
        df = frame.dropna(subset=["계약일", "거래금액_만원"]).sort_values("계약일")
        color = colors[index % len(colors)]
        symbol = symbols[index % len(symbols)]
        if df.empty:
            fig.add_trace(go.Scatter(x=[], y=[], mode="markers", name=label, legendgroup=label,
                                    marker=dict(color=color, size=8, symbol=symbol)))
            continue
        prices = df["거래금액_만원"].astype(float) / 10000
        fig.add_trace(go.Scatter(x=df["계약일"], y=prices, mode="markers", name=label,
                                legendgroup=label, marker=dict(color=color, size=8, opacity=.7, symbol=symbol),
                                customdata=df[["전용면적_num", "층_num"]].to_numpy(),
                                hovertemplate="%{x|%Y-%m-%d}<br>%{y:.2f}억<br>%{customdata[0]:.2f}㎡ · %{customdata[1]}층<extra>%{fullData.name}</extra>"))
        if len(df) >= 4:
            window = max(5, min(15, len(df)//6))
            median = prices.rolling(window, center=True, min_periods=1).median()
            fig.add_trace(go.Scatter(x=df["계약일"], y=median, mode="lines", name=label,
                                    legendgroup=label, showlegend=False, line=dict(color=color, width=2.6)))
    left, right = date_bounds(start, end)
    months = (right.year - left.year) * 12 + (right.month - left.month) + 1
    dtick = "M12" if months > 132 else ("M6" if months >= 120 else "M3")
    title = f"{int(area)}㎡ 매매 실거래가 비교" if area is not None else "매매 실거래가 비교"
    fig.update_layout(title=dict(text=title, font=dict(size=16)), height=430,
                      margin=dict(l=45, r=15, t=80, b=35),
                      paper_bgcolor="white", plot_bgcolor="white", hovermode="closest",
                      legend=dict(orientation="h", x=1, xanchor="right", y=1.02, yanchor="bottom", font=dict(size=11)),
                      xaxis=dict(range=[left, right + pd.Timedelta(days=1)], tickformat="%y.%m",
                                 dtick=dtick, gridcolor="#eeeeee"),
                      yaxis=dict(ticksuffix="억", gridcolor="#eeeeee", zeroline=False))
    return shade_downturns(fig, start, end)
