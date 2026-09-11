"""서울 KB 아파트 월별 매매가격지수로 계산한 공통 시장 국면."""
import json
from pathlib import Path
import pandas as pd

FIRST_YEAR, LAST_YEAR = 2006, 2025
HISTORY_SOURCE = "https://ecos.bok.or.kr/api/StatisticSearch/sample/json/kr/1/10/901Y062/M/202506/202512/P63ACA/"
SHADE = "rgba(128, 128, 128, 0.18)"
_DATA = json.loads((Path(__file__).parent / "data/seoul_market_monthly.json").read_text())
_INDEX = {row["month"]: row["index"] for row in _DATA["rows"]}


def _direction(end, previous):
    delta = _INDEX[end] - _INDEX[previous]
    return "하락기" if delta < 0 else "상승기" if delta > 0 else "보합"


def market_phase(year):
    if FIRST_YEAR <= year <= LAST_YEAR:
        return _direction(f"{year}-12", f"{year - 1}-12")
    return "미분류"


def half_phase(date):
    date = pd.Timestamp(date)
    if pd.isna(date) or not FIRST_YEAR <= date.year <= LAST_YEAR:
        return "미분류"
    year = date.year
    return (_direction(f"{year}-06", f"{year-1}-12") if date.month <= 6
            else _direction(f"{year}-12", f"{year}-06"))


DOWN_YEARS = frozenset(y for y in range(FIRST_YEAR, LAST_YEAR + 1) if market_phase(y) == "하락기")


def phase_mark(value):
    if value == "상승기":
        return "(+)"
    if value == "하락기":
        return "(-)"
    return value


def phase_badge_colors(value):
    if value == "상승기":
        return "#fee2e2", "#9f1239"
    if value == "하락기":
        return "#dbeafe", "#1e40af"
    return "#f4f5f7", "#586372"


def shade_downturns(fig, start, end):
    start = pd.Timestamp(str(start)[:7] + "-01")
    end = pd.Timestamp(str(end)[:7] + "-01") + pd.offsets.MonthBegin(1)
    for year in range(FIRST_YEAR, LAST_YEAR + 1):
        for month in (1, 7):
            boundary = pd.Timestamp(year, month, 1)
            if half_phase(boundary) != "하락기":
                continue
            left, right = max(start, boundary), min(end, boundary + pd.DateOffset(months=6))
            if left < right:
                fig.add_vrect(x0=left.isoformat(), x1=right.isoformat(), fillcolor=SHADE,
                              line_width=0, layer="below")
    return fig


def annual_activity(df, start, end):
    dates = pd.to_datetime(df["계약일"], errors="coerce")
    counts = dates[dates.dt.to_period("M").isin(pd.period_range(start, end, freq="M"))].dt.year.value_counts()
    return pd.DataFrame([
        {"연도": str(year), "서울 시장": market_phase(year),
         "상반기": half_phase(f"{year}-01-01"), "하반기": half_phase(f"{year}-07-01"),
         "조회된 거래 건수": int(counts.get(year, 0))}
        for year in range(max(FIRST_YEAR, int(start[:4])), min(LAST_YEAR, int(end[:4])) + 1)
    ])


def phase_comparison(df, start, end):
    """거래 없는 달도 포함한 반기 국면별 연환산 거래 건수."""
    months = pd.period_range(start, end, freq="M")
    dates = pd.to_datetime(df["계약일"], errors="coerce")
    phases = dates[dates.dt.to_period("M").isin(months)].map(half_phase)
    rows = []
    for phase in ["상승기", "하락기"]:
        duration = sum(half_phase(month.start_time) == phase for month in months)
        count = int((phases == phase).sum())
        rows.append({"시장 국면": phase, "비교 기간(개월)": duration, "거래 건수": count,
                     "연평균 거래 건수(연환산)": round(count * 12 / duration, 2) if duration else None})
    return pd.DataFrame(rows)
