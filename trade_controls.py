"""실거래 화면의 공통 기간·면적 선택 규칙."""
import pandas as pd
import streamlit as st

PRESETS = [("최근 10년", 120), ("최근 5년", 60), ("최근 3년", 36),
           ("최근 1년", 12), ("최근 6개월", 6), ("최근 3개월", 3)]


def today():
    return pd.Timestamp.now(tz="Asia/Seoul").tz_localize(None).normalize()


def recent_range(months, now=None):
    now = pd.Timestamp(now) if now is not None else today()
    end = now.to_period("M")
    return str(end - (months - 1)), str(end)


def date_bounds(start, end, now=None):
    now = pd.Timestamp(now) if now is not None else today()
    return pd.Timestamp(start + "-01"), min(pd.Timestamp(end + "-01") + pd.offsets.MonthEnd(0), now.normalize())


def as_period_range(value):
    """select_slider는 한 달만 고르면 문자열이 되므로 항상 (시작, 끝)으로 맞춘다."""
    if isinstance(value, (list, tuple)):
        if len(value) >= 2:
            start, end = str(value[0]), str(value[-1])
            return (end, start) if start > end else (start, end)
        if len(value) == 1 and value[0] not in (None, ""):
            text = str(value[0])
            return text, text
        return None
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    text = str(value)
    if not text or text in {"nan", "None", "<NA>"}:
        return None
    return text, text


def is_collapsed_start(value, options):
    """select_slider가 범위 대신 첫 달(2006-01) 하나만 남긴 상태인지."""
    parsed = as_period_range(value)
    if not parsed or not options:
        return True
    start, end = parsed
    return start == end == str(options[0])


def ensure_period_state(slider_key, options, now=None):
    """위젯 키가 없거나 첫 달로 접혔으면 최근 10년으로 되돌린다."""
    now = pd.Timestamp(now) if now is not None else today()
    stored = as_period_range(st.session_state.get(slider_key))
    if stored is None or is_collapsed_start(stored, options):
        stored = recent_range(120, now)
        st.session_state[slider_key] = stored
    return stored


def period_presets(key):
    now = today()
    options = pd.period_range("2006-01", now, freq="M").astype(str).tolist()
    slider_key = key + "_range"
    current = ensure_period_state(slider_key, options, now)
    presets = [("전체", None)] + PRESETS
    clicked = None
    for col, (label, months) in zip(st.columns(len(presets)), presets):
        target = recent_range(months, now) if months else (options[0], options[-1])
        if col.button(label, key=f"{key}_preset_{months}",
                      type="primary" if current == tuple(target) else "secondary",
                      use_container_width=True):
            clicked = target
    if clicked:
        st.session_state[slider_key] = clicked
        st.rerun()


def period_slider(key, label="기간 (년월)"):
    now = today()
    options = pd.period_range("2006-01", now, freq="M").astype(str).tolist()
    slider_key = key + "_range"
    current = ensure_period_state(slider_key, options, now)
    selected = as_period_range(st.select_slider(label, options=options, key=slider_key)) or current
    if is_collapsed_start(selected, options):
        return current
    return selected


def period_control(key):
    period_presets(key)
    start, end = period_slider(key)
    left, right = date_bounds(start, end)
    st.caption(f"{left:%Y-%m-%d} ~ {right:%Y-%m-%d} · 최근 기간은 시작 월 1일부터 오늘까지입니다.")
    return start, end


def area_values(frame, grouped=False):
    values = pd.to_numeric(frame["전용면적_num"], errors="coerce")
    return values.floordiv(1) if grouped else values


def grouped_chart_frame(frame):
    result = frame.copy()
    result["전용면적_num"] = area_values(frame, True)
    return result


def area_label(value, grouped=False):
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return "면적미상"
    try:
        num = float(value)
    except (TypeError, ValueError):
        return "면적미상"
    if grouped:
        return f"{int(num)}㎡"
    if num.is_integer():
        return f"{num:.0f}㎡"
    return f"{num:.2f}㎡"
