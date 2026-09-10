"""서울 아파트 시장의 연간 방향. 단지 실거래로 시장 국면을 추정하지 않는다.

2006~2024: 한국부동산원 전국주택가격동향조사 서울 아파트 매매가격지수,
KOSIS 연말값을 재게시한 DATA CLOCK KOREA에서 방향 확인.
2025: 2025년 12월 전국주택가격동향조사 연간 +8.98% 보도에서 방향 확인.
연간 음수인 해를 하락기로 정의하며, 월별 전환일 또는 전국 부동산 국면은 아니다.
확인일: 2026-09-11. 2026년 이후는 자동으로 상승기로 추정하지 않는다.
"""
import pandas as pd

FIRST_YEAR = 2006
LAST_YEAR = 2025
DOWN_YEARS = frozenset({2010, 2011, 2012, 2013, 2022, 2023})
HISTORY_SOURCE = "https://www.dataclockkorea.com/real-estate/seoul/"
RECENT_SOURCE = "https://www.seoul.co.kr/news/economy/estate/2026/01/27/20260127032003"
SHADE = "rgba(128, 128, 128, 0.18)"


def market_phase(year):
    if FIRST_YEAR <= year <= LAST_YEAR:
        return "하락기" if year in DOWN_YEARS else "상승기"
    return "미분류"


def shade_downturns(fig, start, end):
    """Clip yearly background rectangles to the selected range, behind all data."""
    start = pd.Timestamp(str(start)[:7] + "-01")
    end = pd.Timestamp(str(end)[:7] + "-01") + pd.offsets.MonthBegin(1)
    for year in sorted(DOWN_YEARS):
        left = max(start, pd.Timestamp(year, 1, 1))
        right = min(end, pd.Timestamp(year + 1, 1, 1))
        if left < right:
            fig.add_vrect(
                x0=left.isoformat(), x1=right.isoformat(), fillcolor=SHADE,
                line_width=0, layer="below",
            )
    return fig


def annual_activity(df, start, end):
    """Counts are from available, filtered records, not a claim of complete coverage."""
    dates = pd.to_datetime(df["계약일"], errors="coerce")
    counts = dates.dt.year.value_counts()
    return pd.DataFrame([
        {"연도": str(year), "서울 시장": market_phase(year),
         "조회된 거래 건수": int(counts.get(year, 0))}
        for year in range(max(FIRST_YEAR, int(start[:4])), min(LAST_YEAR, int(end[:4])) + 1)
    ])


def phase_comparison(df, start, end):
    """Annualized counts using all selected months, including zero-trade months."""
    months = pd.period_range(start, end, freq="M")
    dates = pd.to_datetime(df["계약일"], errors="coerce")
    selected = df.loc[dates.dt.to_period("M").isin(months)]
    phases = pd.to_datetime(selected["계약일"], errors="coerce").dt.year.map(
        lambda year: market_phase(int(year)) if pd.notna(year) else "미분류"
    )
    rows = []
    for phase in ["상승기", "하락기"]:
        duration = sum(market_phase(month.year) == phase for month in months)
        count = int((phases == phase).sum())
        rows.append({"시장 국면": phase, "비교 기간(개월)": duration,
                     "거래 건수": count,
                     "연평균 거래 건수(연환산)": round(count * 12 / duration, 2) if duration else None})
    return pd.DataFrame(rows)
