"""Fetch public ECOS sample API in its permitted <=10-row date windows."""
import json
import time
from pathlib import Path
import requests

BASE = "https://ecos.bok.or.kr/api/StatisticSearch/sample/json/kr/1/10/901Y062/M"

def main():
    months = [f"{year}{month:02}" for year in range(2005, 2026) for month in range(1, 13) if (year, month) >= (2005, 12)]
    rows = []
    for offset in range(0, len(months), 10):
        batch = months[offset:offset+10]
        response = requests.get(f"{BASE}/{batch[0]}/{batch[-1]}/P63ACA/", timeout=25)
        response.raise_for_status()
        result = response.json()["StatisticSearch"]
        values = result["row"]
        assert len(values) == len(batch)
        assert all(row["ITEM_CODE1"] == "P63ACA" for row in values)
        rows.extend({"month": row["TIME"][:4]+"-"+row["TIME"][4:],
                     "index": float(row["DATA_VALUE"])} for row in values)
        time.sleep(0.2)
    assert len(rows) == 241 and len({r["month"] for r in rows}) == 241
    out = {"source": "한국은행 ECOS / KB국민은행", "stat_code": "901Y062", "item_code": "P63ACA",
           "unit": "2026.01=100", "retrieved": "2026-09-11",
           "source_url": "https://ecos.bok.or.kr/",
           "method": "반기 마지막 월 지수를 직전 반기 마지막 월 지수와 비교; 음수이면 하락기",
           "rows": sorted(rows, key=lambda r:r["month"])}
    (Path(__file__).resolve().parents[1] / "data/seoul_market_monthly.json").write_text(json.dumps(out, ensure_ascii=False, indent=2))
    print("Saved", len(rows), "official monthly observations")


if __name__ == "__main__":
    main()
