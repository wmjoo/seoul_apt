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


def period_control(key):
    now = today()
    options = pd.period_range("2006-01", now, freq="M").astype(str).tolist()
    slider_key = key + "_range"
    if slider_key not in st.session_state:
        st.session_state[slider_key] = recent_range(120, now)
    presets = [("전체", None)] + PRESETS
    current = tuple(st.session_state[slider_key])
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
    start, end = st.select_slider("기간 (년월)", options=options, key=slider_key)
    left, right = date_bounds(start, end, now)
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
