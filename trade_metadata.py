"""단지 식별과 표시용 메타정보. 거래별 값은 단지 정보에서 제외한다."""
import re
import pandas as pd


def name_key(value):
    return re.sub(r"\s+|아파트", "", str(value)).replace("에스케이", "SK").upper()


def complex_metadata(trades, apartments=None):
    result = {}
    for col in ["아파트명", "법정동", "지번", "도로명", "건축년도"]:
        if col in trades:
            values = trades[col].dropna().astype(str).str.strip()
            values = values[~values.isin(["", "nan", "None", "<NA>"])].unique()
            if len(values):
                result[col] = " / ".join(values)
    if apartments is not None and not apartments.empty and "아파트명" in apartments and not trades.empty:
        matches = apartments[apartments["아파트명"].map(name_key) == name_key(trades.iloc[0].get("아파트명", ""))]
        for source, target in [("구", "자치구"), ("법정동", "동")]:
            if source in trades and target in matches:
                allowed = set(trades[source].dropna().astype(str))
                matches = matches[matches[target].astype(str).isin(allowed)]
        # Ambiguous matches are not silently combined.
        matches = matches.drop_duplicates()
        if len(matches) == 1:
            for col in ["주소", "건축연도", "세대수", "복도계단식", "난방방식", "건설사",
                        "주차대수", "세대당주차면수", "가장가까운지하철역", "지하철역거리_km"]:
                value = matches.iloc[0].get(col)
                if pd.notna(value) and str(value).strip():
                    if col == "건축연도" and "건축년도" in result:
                        continue
                    result[col] = value
    return pd.DataFrame([result]) if result else pd.DataFrame()
