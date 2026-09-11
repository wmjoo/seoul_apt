"""인증된 사용자의 단지별 거래 비교 화면."""
from contextlib import nullcontext

import pandas as pd
import streamlit as st
from trade_controls import period_control, date_bounds, area_values, grouped_chart_frame
from trade_metadata import name_key
from market_cycles import shade_downturns


def common_areas(frames):
    sets = [set(area_values(df, True).dropna().astype(int)) for df in frames]
    return sorted(set.intersection(*sets)) if sets else []


def preferred_overlay_area(frames, shared):
    if not shared:
        return None
    values = pd.concat([area_values(df, True) for df in frames], ignore_index=True)
    ranked = values[values.isin(shared)].value_counts()
    return int(ranked.index[0]) if len(ranked) else int(shared[0])


OVERLAY_SYMBOLS = ["circle", "diamond", "square", "x", "triangle-up"]
COMPARE_TABLE_COLS = ["전용면적", "평", "층", "거래가격", "계약일"]


def overlay_colors(count):
    palettes = {
        1: ["#2563EB"],
        2: ["#0072B2", "#D55E00"],
        3: ["#0072B2", "#D55E00", "#009E73"],
        4: ["#0072B2", "#D55E00", "#009E73", "#CC79A7"],
    }
    fallback = ["#0072B2", "#D55E00", "#009E73", "#CC79A7", "#E69F00", "#56B4E9"]
    return palettes.get(count, fallback[:count])


def overlay_style(index, count):
    colors = overlay_colors(count)
    return colors[index % len(colors)], OVERLAY_SYMBOLS[index % len(OVERLAY_SYMBOLS)]


def _format_trade_price(value):
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


def format_compare_table(frame):
    if frame is None or frame.empty:
        return pd.DataFrame(columns=COMPARE_TABLE_COLS)
    work = frame.copy()
    if "전용면적" not in work.columns and "전용면적_num" in work.columns:
        work["전용면적"] = work["전용면적_num"]
    if "층" not in work.columns and "층_num" in work.columns:
        work["층"] = work["층_num"]
    if "평" not in work.columns:
        area = pd.to_numeric(work["전용면적"] if "전용면적" in work.columns else work.get("전용면적_num"), errors="coerce")
        work["평"] = (area / 3.3058).round(1)
    if "거래가격" not in work.columns:
        price = work["거래금액_만원"] if "거래금액_만원" in work.columns else work.get("거래금액")
        work["거래가격"] = pd.to_numeric(price, errors="coerce").map(_format_trade_price)
    work["계약일"] = pd.to_datetime(work.get("계약일"), errors="coerce").dt.strftime("%Y-%m-%d")
    if "전용면적" in work.columns:
        area = pd.to_numeric(work["전용면적"], errors="coerce")
        work["전용면적"] = area.map(lambda x: "" if pd.isna(x) else (f"{x:.0f}" if float(x).is_integer() else f"{float(x):.2f}"))
    if "층" in work.columns:
        floor = pd.to_numeric(work["층"], errors="coerce")
        work["층"] = floor.map(lambda x: "" if pd.isna(x) else str(int(x)))
    cols = [c for c in COMPARE_TABLE_COLS if c in work.columns]
    return work.sort_values("계약일", ascending=False, na_position="last")[cols].reset_index(drop=True)


def filter_comparison(frame, start, end, area="전체", exclude_first=False):
    left, right = date_bounds(start, end)
    result = frame.loc[pd.to_datetime(frame["계약일"]).between(left, right + pd.Timedelta(days=1), inclusive="left")]
    if area != "전체":
        result = result.loc[area_values(result, True) == int(area)]
    if exclude_first:
        result = result.loc[result["층_num"] != 1]
    return result


def display_label(labels, key):
    """Streamlit format_func/정렬 키는 None을 허용하지 않는다."""
    label = labels.get(key)
    if label:
        return label
    return str(key) if pd.notna(key) else "(단지 미상)"


def complex_options(frame, labels):
    values = (
        frame["_complex"].dropna().astype(str).loc[lambda s: ~s.isin(["", "nan", "None", "<NA>"])]
        .unique()
        .tolist()
    )
    return sorted(values, key=lambda key: display_label(labels, key))


def area_choices(shared):
    return ["전체"] + [str(int(value)) for value in shared]


def parse_area_choice(value):
    return "전체" if value in (None, "전체") else int(value)


SESSION_KEY_COMPARE_PICKED = "compare_picked"
SESSION_KEY_COMPARE_SHOW = "compare_show"
SESSION_KEY_COMPARE_SEEDED = "compare_seeded"
SESSION_KEY_COMPARE_BUSY = "compare_busy"
SESSION_KEY_COMPARE_FORCE = "compare_force"
COMPARE_MAX = 4
DEFAULT_COMPARE_HINTS = (
    {"gu": "성북구", "tokens": ("성북구", "종암동", "종암에스케이")},
    {"gu": "동대문구", "tokens": ("동대문구", "청량리동", "한신"), "exclude": ("1차",)},
)


def _align_button():
    st.markdown("<div style='height:1.7rem'></div>", unsafe_allow_html=True)


def match_complex_key(options, tokens, exclude=()):
    matches = [key for key in options if all(token in str(key) for token in tokens)]
    if not matches:
        return None
    if exclude:
        narrowed = [key for key in matches if not any(token in str(key) for token in exclude)]
        if narrowed:
            matches = narrowed
    return sorted(matches, key=len)[0]


def _with_complex_key(frame):
    identity = [c for c in ["구", "법정동", "아파트명", "지번"] if c in frame]
    if "아파트명" not in identity:
        return pd.DataFrame()
    result = frame.copy()
    result["_complex"] = result[identity].fillna("").astype(str).agg(" | ".join, axis=1)
    return result


def pick_id(item):
    if item.get("key"):
        return str(item["key"])
    tokens = tuple(item.get("tokens") or ())
    return "|".join(tokens) if tokens else item.get("label", "")


def _hint_label(apartments, hint):
    gu, tokens = hint["gu"], hint["tokens"]
    name = tokens[-1] if tokens else gu
    dong = next((t for t in tokens if str(t).endswith("동")), "")
    label = f"{name}({gu} {dong})".strip()
    options, labels = apartment_options_for_gu(apartments, gu)
    if not options:
        return f"{label} [세대수 미상]" if "[" not in label else label
    key = match_complex_key(options, tokens, hint.get("exclude", ()))
    if key:
        return labels.get(key, label)
    return f"{label} [세대수 미상]"


def seed_compare_picks(apartments=None, district_names=None, hints=DEFAULT_COMPARE_HINTS):
    names = {str(x).strip() for x in (district_names or []) if str(x).strip()}
    picks = []
    for hint in hints:
        if names and hint["gu"] not in names:
            continue
        picks.append({
            "gu": hint["gu"],
            "tokens": hint["tokens"],
            "exclude": hint.get("exclude", ()),
            "label": _hint_label(apartments, hint),
        })
    return picks


def apartment_options_for_gu(apartments, gu):
    if apartments is None or getattr(apartments, "empty", True):
        return [], {}
    gu_col = "자치구" if "자치구" in apartments.columns else ("구" if "구" in apartments.columns else None)
    dong_col = "동" if "동" in apartments.columns else ("법정동" if "법정동" in apartments.columns else None)
    if not gu_col or "아파트명" not in apartments.columns:
        return [], {}
    cols = ["아파트명", gu_col] + ([dong_col] if dong_col else [])
    if "세대수" in apartments.columns:
        cols.append("세대수")
    work = apartments.loc[apartments[gu_col].astype(str).str.strip() == str(gu).strip(), cols].copy()
    if work.empty:
        return [], {}
    work["아파트명"] = work["아파트명"].astype(str).str.strip()
    work[gu_col] = work[gu_col].astype(str).str.strip()
    if dong_col:
        work[dong_col] = work[dong_col].astype(str).str.strip()
    work = work.loc[work["아파트명"].ne("") & ~work["아파트명"].isin(["nan", "None", "<NA>"])]
    parts = [work[gu_col], work[dong_col], work["아파트명"]] if dong_col else [work[gu_col], work["아파트명"]]
    work = work.copy()
    work["_key"] = parts[0]
    for part in parts[1:]:
        work["_key"] = work["_key"] + " | " + part
    first = work.drop_duplicates("_key", keep="first")
    labels = {}
    for _, row in first.iterrows():
        key = str(row["_key"])
        name = str(row["아파트명"]).strip()
        dong = str(row[dong_col]).strip() if dong_col else ""
        count = pd.to_numeric(row.get("세대수"), errors="coerce") if "세대수" in first.columns else pd.NA
        household = f"{int(count):,}세대" if pd.notna(count) and count > 0 else "세대수 미상"
        labels[key] = f"{name}({gu} {dong}) [{household}]" if dong else f"{name}({gu}) [{household}]"
    options = sorted(labels, key=lambda key: labels[key])
    return options, labels


def pick_from_option(gu, option_key, labels):
    parts = [p.strip() for p in str(option_key).split("|")]
    tokens = tuple(p for p in parts if p)
    name = parts[-1] if parts else option_key
    exclude = ("1차",) if "1차" not in name else ()
    return {
        "gu": gu,
        "tokens": tokens,
        "exclude": exclude,
        "label": display_label(labels, option_key),
    }


def default_compare_picks(frame, apartments=None, hints=DEFAULT_COMPARE_HINTS):
    if frame is None or frame.empty:
        return []
    keyed = frame if "_complex" in frame.columns else _with_complex_key(frame)
    if keyed.empty:
        return []
    labels = complex_labels(keyed, apartments)
    options = complex_options(keyed, labels)
    picks = []
    seen = set()
    for hint in hints:
        key = match_complex_key(options, hint["tokens"], hint.get("exclude", ()))
        if not key or key in seen:
            continue
        seen.add(key)
        picks.append({
            "key": key,
            "gu": hint["gu"],
            "tokens": hint["tokens"],
            "exclude": hint.get("exclude", ()),
            "label": display_label(labels, key),
        })
    return picks


def _announce(busy, message, status=None):
    if not busy:
        return
    st.toast(message)
    if status is not None:
        status.update(label=message, state="running")
        status.write(message)


def render_trade_compare(load_data, prepare, volume_chart, apartments=None, district_names=None):
    names = [str(x).strip() for x in (district_names or []) if str(x).strip()]
    picked = st.session_state.setdefault(SESSION_KEY_COMPARE_PICKED, [])
    _, refresh_col = st.columns([8, 2])
    refresh = refresh_col.button("최신 데이터 불러오기", key="compare_refresh", use_container_width=True)
    if not names:
        st.info("저장된 실거래가 없습니다. 크롤링 탭에서 구를 추가해 주세요.")
        return
    if not st.session_state.get(SESSION_KEY_COMPARE_SEEDED):
        if not picked:
            picked.extend(seed_compare_picks(apartments, names))
        st.session_state[SESSION_KEY_COMPARE_SEEDED] = True
        st.session_state[SESSION_KEY_COMPARE_SHOW] = False
    if refresh:
        st.session_state[SESSION_KEY_COMPARE_SHOW] = False
        st.session_state[SESSION_KEY_COMPARE_FORCE] = True
        st.toast("최신 데이터를 다시 받습니다. 비교를 누르면 적용됩니다.")
        st.caption("비교를 누르면 선택한 단지의 실거래를 다시 읽습니다.")
    default_gu = "성북구" if "성북구" in names else names[0]
    gcol, ccol, add_col = st.columns([2.0, 3.4, 0.8])
    with gcol:
        selected_gu = st.selectbox("구", names, index=names.index(default_gu), key="compare_gu")
    options, labels = apartment_options_for_gu(apartments, selected_gu)
    picked_ids = {pick_id(item) for item in picked}
    options = [key for key in options if pick_id(pick_from_option(selected_gu, key, labels)) not in picked_ids
               and key not in picked_ids
               and display_label(labels, key) not in {item.get("label") for item in picked}]
    with ccol:
        if options:
            preferred = match_complex_key(options, DEFAULT_COMPARE_HINTS[0]["tokens"]) or options[0]
            selected_apt = st.selectbox(
                "단지",
                options,
                index=options.index(preferred) if preferred in options else 0,
                key=f"compare_apt_{selected_gu}",
                format_func=lambda key: display_label(labels, key),
            )
        else:
            selected_apt = None
            st.selectbox("단지", ["추가할 단지가 없습니다."], disabled=True, key=f"compare_apt_empty_{selected_gu}")
    with add_col:
        _align_button()
        if st.button("추가", width="stretch", disabled=not selected_apt or len(picked) >= COMPARE_MAX, key="compare_add"):
            if len(picked) >= COMPARE_MAX:
                st.warning(f"단지는 최대 {COMPARE_MAX}개까지 비교할 수 있습니다.")
            elif selected_apt:
                picked.append(pick_from_option(selected_gu, selected_apt, labels))
                st.session_state[SESSION_KEY_COMPARE_SHOW] = False
                st.rerun()

    list_col, go_col = st.columns([5.2, 0.8])
    with list_col:
        if not picked:
            st.caption("단지를 추가한 뒤 비교를 누르세요.")
        else:
            st.caption("비교를 눌러야 실거래를 읽고 차트를 그립니다.")
            for i, item in enumerate(list(picked)):
                name_col, del_col = st.columns([10, 1])
                with name_col:
                    st.markdown(item["label"])
                with del_col:
                    if st.button("×", key=f"compare_remove_{i}", width="stretch"):
                        picked.pop(i)
                        st.session_state[SESSION_KEY_COMPARE_SHOW] = False
                        st.rerun()
    with go_col:
        _align_button()
        if st.button("비교", width="stretch", disabled=len(picked) < 2, key="compare_run"):
            st.session_state[SESSION_KEY_COMPARE_SHOW] = True
            st.session_state[SESSION_KEY_COMPARE_BUSY] = True
            st.rerun()

    if not st.session_state.get(SESSION_KEY_COMPARE_SHOW) or len(picked) < 2:
        return
    busy = bool(st.session_state.get(SESSION_KEY_COMPARE_BUSY))
    gus = list(dict.fromkeys(item["gu"] for item in picked))
    force = refresh or bool(st.session_state.get(SESSION_KEY_COMPARE_FORCE))
    status = st.status("비교를 준비하는 중", expanded=True) if busy else None
    _announce(busy, f"{'·'.join(gus)} 실거래를 불러오는 중", status)
    try:
        with st.spinner(f"{'·'.join(gus)} 실거래를 불러오는 중") if busy else nullcontext():
            combined = _load_compare_frame(picked, load_data, prepare, force)
    except Exception:
        if status is not None:
            status.update(label="실거래를 읽지 못했습니다", state="error")
        st.error("비교할 실거래를 읽지 못했습니다. 잠시 후 다시 불러와 주세요.")
        st.session_state[SESSION_KEY_COMPARE_BUSY] = False
        return
    st.session_state[SESSION_KEY_COMPARE_FORCE] = False
    _announce(busy, "선택한 단지를 찾는 중", status)
    frames, resolved = _resolve_picked_frames(combined, picked)
    picked[:] = resolved
    if combined.empty or any(df.empty for df in frames):
        missing = [item.get("label") or item.get("gu") for item, df in zip(resolved, frames) if df.empty]
        if status is not None:
            status.update(label="단지 거래를 찾지 못했습니다", state="error")
        st.warning("추가한 단지의 거래를 찾지 못했습니다: " + ", ".join(missing))
        st.session_state[SESSION_KEY_COMPARE_BUSY] = False
        return
    _announce(busy, "기간·면적을 적용하는 중", status)
    _render_compare_results(resolved, frames, combined, volume_chart, busy=busy, status=status)
    if status is not None:
        status.update(label="비교 완료", state="complete", expanded=False)
    if busy:
        st.toast("비교 완료")
        st.session_state[SESSION_KEY_COMPARE_BUSY] = False


def _load_compare_frame(picked, load_data, prepare, force):
    gus = list(dict.fromkeys(item["gu"] for item in picked))
    frame = prepare(load_data(force=force, districts=gus))
    if frame is None or frame.empty:
        return pd.DataFrame()
    return _with_complex_key(frame)


def _resolve_picked_frames(frame, picked):
    if frame is None or frame.empty or "_complex" not in frame.columns:
        return [pd.DataFrame() for _ in picked], list(picked)
    options = frame["_complex"].dropna().astype(str).unique().tolist()
    known = set(options)
    frames = []
    resolved = []
    for item in picked:
        key = item.get("key") if item.get("key") in known else None
        if not key:
            key = match_complex_key(options, item.get("tokens") or (), item.get("exclude") or ())
        part = frame.loc[frame["_complex"] == key].copy() if key else frame.iloc[0:0].copy()
        frames.append(part)
        resolved.append({**item, "key": key})
    return frames, resolved


def _frames_for_picked(picked, load_data, prepare, force):
    frame = _load_compare_frame(picked, load_data, prepare, force)
    frames, resolved = _resolve_picked_frames(frame, picked)
    return frame, frames, resolved


def _render_compare_results(picked, frames, combined, volume_chart, busy=False, status=None):
    selected = [item.get("key") for item in picked]
    labels = {item["key"]: item["label"] for item in picked if item.get("key")}
    valid_dates = combined["계약일"].dropna() if "계약일" in combined.columns else pd.Series(dtype="datetime64[ns]")
    if valid_dates.empty:
        st.info("비교할 거래 날짜가 없습니다.")
        return
    start, end = period_control("compare_period")
    area_col, floor_col = st.columns([3, 1])
    shared = common_areas(frames)
    area_options = [str(int(value)) for value in shared]
    if area_options:
        overlay_default = preferred_overlay_area(frames, shared)
        default_area = str(int(overlay_default)) if overlay_default is not None else area_options[0]
        if st.session_state.get("compare_area") not in area_options:
            st.session_state.pop("compare_area", None)
        area = parse_area_choice(area_col.selectbox(
            "전용면적",
            area_options,
            index=area_options.index(default_area) if default_area in area_options else 0,
            format_func=lambda x: f"{x}㎡",
            key="compare_area",
        ))
    else:
        area = "전체"
        area_col.selectbox("전용면적", ["공통 면적 없음"], disabled=True, key="compare_area_empty")
    exclude = floor_col.checkbox("1층 제외", key="compare_exclude_first")
    st.caption("소수점을 버린 정수 면적(59·84·114㎡)으로 묶어 비교합니다. 기간·면적·1층 제외는 아래 차트와 표에 같이 적용됩니다.")
    if not shared:
        st.caption("공통 전용면적이 없어 전체 면적으로 비교합니다.")
    views = [filter_comparison(df, start, end, area, exclude) for df in frames]
    named = [display_label(labels, x) for x in selected]
    _announce(busy, "반기별 건수 표를 만드는 중", status)
    st.markdown("**반기별 거래 건수**")
    st.dataframe(half_year_activity(views, named, start, end),
                 hide_index=True, use_container_width=True)
    st.caption("현재 필터와 저장된 거래 기준입니다. 0건에는 미수집 기간이 포함될 수 있습니다.")
    st.markdown("**단지별 매매 실거래가 비교**")
    if shared:
        _announce(busy, "실거래가 차트를 그리는 중", status)
        st.plotly_chart(build_overlay(views, named, start, end, area),
                        use_container_width=True, key="compare_overlay",
                        config={"displaylogo": False, "scrollZoom": True})
        _announce(busy, "월별 건수 차트를 그리는 중", status)
        st.plotly_chart(build_overlay_volume(views, named, start, end, area),
                        use_container_width=True, key="compare_overlay_volume",
                        config={"displaylogo": False, "scrollZoom": True})
        st.caption("선·점은 단지별 실거래와 이동 중앙값, 아래는 같은 면적의 월별 거래 건수입니다. 색·모양은 단지별로 같습니다.")
    else:
        st.info("공통 정수 면적이 없어 동일 면적 통합 차트를 표시할 수 없습니다.")
    _announce(busy, "단지별 거래 표를 만드는 중", status)
    filtered = pd.concat(views) if views else combined
    palette = sorted(area_values(filtered, True).dropna().unique()) if not filtered.empty else []
    counts = [int(df.groupby("계약년월").size().max()) if not df.empty else 0 for df in views]
    columns = st.columns(len(selected))
    for i, (col, label, df) in enumerate(zip(columns, selected, views)):
        with col:
            st.markdown(f"**{display_label(labels, label)}**")
            st.caption(f"{start} ~ {end} · {len(df):,}건")
            volume = volume_chart(grouped_chart_frame(df), start, end, palette)
            volume.update_yaxes(range=[0, max(1, max(counts)) * 1.2])
            st.plotly_chart(volume, use_container_width=True, key=f"compare_volume_{i}", config={"displaylogo": False})
            table = format_compare_table(df)
            st.dataframe(table, hide_index=True, use_container_width=True, height=360)
            st.download_button("원본 내역 CSV", table.to_csv(index=False).encode("utf-8-sig"),
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
    first_rows = frame.drop_duplicates("_complex", keep="first")

    def column(name):
        if name in first_rows:
            return first_rows[name]
        return pd.Series([""] * len(first_rows), index=first_rows.index)

    keys = first_rows["_complex"].astype(str)
    names, gus, dongs, bunjis = column("아파트명"), column("구"), column("법정동"), column("지번")
    own_counts = pd.to_numeric(column("세대수"), errors="coerce")
    labels = {}
    for key, name, gu, dong, own_count in zip(keys, names, gus, dongs, own_counts):
        if key in ("", "nan", "None", "<NA>"):
            continue
        name, gu, dong = [str(value).strip() for value in (name, gu, dong)]
        counts = household_lookup.get((name_key(name), gu, dong), set())
        if not counts and pd.notna(own_count) and own_count > 0:
            counts = {int(own_count)}
        household = f"{next(iter(counts)):,}세대" if len(counts) == 1 else "세대수 미상"
        labels[key] = f"{name}({gu} {dong}) [{household}]"
    # 이름/동이 같고 지번이 다른 경우에만 식별에 필요한 지번을 덧붙인다.
    duplicate_labels = pd.Series(list(labels.values())).value_counts()
    for key, bunji in zip(keys, bunjis):
        if key in labels and duplicate_labels[labels[key]] > 1:
            labels[key] += f" · {bunji}"
    return labels


def half_year_activity(frames, labels, start, end):
    periods = list(dict.fromkeys((m.year, 1 if m.month <= 6 else 2)
                                for m in pd.period_range(start, end, freq="M")))
    result = pd.DataFrame({"반기": [f"{year} {'상반기' if half == 1 else '하반기'}" for year, half in periods]})
    for label, frame in zip(labels, frames):
        dates = pd.to_datetime(frame["계약일"], errors="coerce").dropna()
        counts = dates.map(lambda d: (d.year, 1 if d.month <= 6 else 2)).value_counts().to_dict()
        result[label] = [int(counts.get(period, 0)) for period in periods]
    return result


def _overlay_axis(start, end):
    left, right = date_bounds(start, end)
    months = (right.year - left.year) * 12 + (right.month - left.month) + 1
    dtick = "M12" if months > 132 else ("M6" if months >= 120 else "M3")
    return left, right, dtick


def monthly_trade_counts(frame, start, end):
    months = pd.period_range(start, end, freq="M")
    empty = pd.Series(0, index=months, dtype=int)
    if frame is None or frame.empty or "계약일" not in frame.columns:
        return empty
    dates = pd.to_datetime(frame["계약일"], errors="coerce").dropna()
    if dates.empty:
        return empty
    counts = dates.dt.to_period("M").value_counts()
    return pd.Series([int(counts.get(month, 0)) for month in months], index=months, dtype=int)


def build_overlay(frames, labels, start, end, area=None):
    import plotly.graph_objects as go
    fig = go.Figure()
    for index, (frame, label) in enumerate(zip(frames, labels)):
        df = frame.dropna(subset=["계약일", "거래금액_만원"]).sort_values("계약일")
        color, symbol = overlay_style(index, len(frames))
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
    left, right, dtick = _overlay_axis(start, end)
    title = f"{int(area)}㎡ 매매 실거래가 비교" if area is not None else "매매 실거래가 비교"
    fig.update_layout(title=dict(text=title, font=dict(size=16)), height=430,
                      margin=dict(l=45, r=15, t=80, b=35),
                      paper_bgcolor="white", plot_bgcolor="white", hovermode="closest",
                      legend=dict(orientation="h", x=1, xanchor="right", y=1.02, yanchor="bottom", font=dict(size=11)),
                      xaxis=dict(range=[left, right + pd.Timedelta(days=1)], tickformat="%y.%m",
                                 dtick=dtick, gridcolor="#eeeeee"),
                      yaxis=dict(ticksuffix="억", gridcolor="#eeeeee", zeroline=False))
    return shade_downturns(fig, start, end)


def build_overlay_volume(frames, labels, start, end, area=None):
    import plotly.graph_objects as go
    fig = go.Figure()
    ymax = 1
    for index, (frame, label) in enumerate(zip(frames, labels)):
        color, symbol = overlay_style(index, len(frames))
        counts = monthly_trade_counts(frame, start, end)
        ymax = max(ymax, int(counts.max()) if len(counts) else 0)
        fig.add_trace(go.Scatter(
            x=counts.index.to_timestamp(),
            y=counts.values,
            mode="lines+markers",
            name=label,
            legendgroup=label,
            line=dict(color=color, width=2.4),
            marker=dict(color=color, size=9, symbol=symbol),
            hovertemplate="%{x|%Y-%m}<br>%{y}건<extra>%{fullData.name}</extra>",
        ))
    left, right, dtick = _overlay_axis(start, end)
    title = f"{int(area)}㎡ 월별 거래 건수 비교" if area is not None else "월별 거래 건수 비교"
    fig.update_layout(title=dict(text=title, font=dict(size=16)), height=320,
                      margin=dict(l=45, r=15, t=72, b=35),
                      paper_bgcolor="white", plot_bgcolor="white", hovermode="x unified",
                      legend=dict(orientation="h", x=1, xanchor="right", y=1.02, yanchor="bottom", font=dict(size=11)),
                      xaxis=dict(range=[left, right + pd.Timedelta(days=1)], tickformat="%y.%m",
                                 dtick=dtick, gridcolor="#eeeeee"),
                      yaxis=dict(title="건수", rangemode="tozero", gridcolor="#eeeeee", zeroline=False,
                                 range=[0, ymax * 1.22]))
    return shade_downturns(fig, start, end)
