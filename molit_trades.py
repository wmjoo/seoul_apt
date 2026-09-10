"""
국토교통부 아파트 매매 실거래(상세) 수집.

조회 단위는 구(LAWD_CD) + 계약년월입니다. 선택한 구의 해당 월 거래를 모두 저장합니다.
"""
from __future__ import annotations

import calendar
import os
import re
import time
import urllib.parse
from datetime import datetime
from typing import Callable, Dict, List, Optional, Sequence, Set, Tuple
from xml.etree import ElementTree as ET

import pandas as pd
import requests

from config import (
    MAX_RETRIES,
    MOLIT_REQUEST_DELAY,
    MOLIT_TRADE_START_YM,
    SEOUL_LAWD_CD,
    TRACKED_COMPLEXES_CSV,
    TRACKED_DISTRICTS_CSV,
    TRADE_HISTORY_CSV,
    get_secret,
)

TRADE_API_URLS = [
    "https://apis.data.go.kr/1613000/RTMSDataSvcAptTradeDev/getRTMSDataSvcAptTradeDev",
    "http://openapi.molit.go.kr/OpenAPI_ToolInstallPackage/service/rest/RTMSOBJSvc/getRTMSDataSvcAptTradeDev",
]

ITEM_FIELDS = {
    "아파트명": ("아파트", "aptNm"),
    "법정동": ("법정동", "umdNm"),
    "지번": ("지번", "jibun"),
    "도로명": ("도로명", "roadNm"),
    "전용면적": ("전용면적", "excluUseAr"),
    "층": ("층", "floor"),
    "거래금액": ("거래금액", "dealAmount"),
    "년": ("년", "dealYear"),
    "월": ("월", "dealMonth"),
    "일": ("일", "dealDay"),
    "건축년도": ("건축년도", "buildYear"),
    "거래유형": ("거래유형", "dealingGbn"),
    "해제여부": ("해제여부", "cdealType"),
    "중개사소재지": ("중개사소재지", "estateAgentSggNm"),
    "지역코드": ("지역코드", "sggCd"),
}

ProgressFn = Callable[[int, int, str], None]


def _decode_service_key(raw: str) -> str:
    key = (raw or "").strip()
    if not key or key.startswith("YOUR_"):
        return ""
    return urllib.parse.unquote(key)


def molit_api_key() -> str:
    """secrets는 요청마다 다시 읽는다. import 시점 캐시를 쓰지 않는다."""
    return _decode_service_key(get_secret("PUBLIC_DATA_API_KEY", "") or "")


def has_molit_api_key() -> bool:
    return bool(molit_api_key())


def _xml_text(el: ET.Element, names: Sequence[str]) -> str:
    for name in names:
        child = el.find(name)
        if child is not None and child.text and child.text.strip():
            return child.text.strip()
    return ""


def _find_text(root: ET.Element, tag: str) -> str:
    el = root.find(f".//{tag}")
    if el is not None and el.text:
        return el.text.strip()
    return ""


def month_range(start_ym: str, end_ym: str) -> List[str]:
    y, m = int(start_ym[:4]), int(start_ym[4:])
    ey, em = int(end_ym[:4]), int(end_ym[4:])
    out = []
    while (y, m) <= (ey, em):
        out.append(f"{y:04d}{m:02d}")
        m += 1
        if m > 12:
            m = 1
            y += 1
    return out


def current_ym() -> str:
    now = datetime.now()
    return f"{now.year:04d}{now.month:02d}"


def months_back(n: int) -> str:
    now = datetime.now()
    y, m = now.year, now.month - (max(n, 1) - 1)
    while m <= 0:
        m += 12
        y -= 1
    return f"{y:04d}{m:02d}"


def ym_to_date_span(start_ym: str, end_ym: str) -> tuple:
    """계약년월 범위를 yyyy-mm-dd ~ yyyy-mm-dd 로 바꾼다. 종료월이 당월이면 오늘까지."""
    start = f"{int(start_ym[:4]):04d}-{int(start_ym[4:]):02d}-01"
    ey, em = int(end_ym[:4]), int(end_ym[4:])
    last = calendar.monthrange(ey, em)[1]
    now = datetime.now()
    if ey == now.year and em == now.month:
        last = min(last, now.day)
    end = f"{ey:04d}-{em:02d}-{last:02d}"
    return start, end


def _parse_price_manwon(raw: str) -> Optional[int]:
    if not raw:
        return None
    digits = re.sub(r"[^\d]", "", str(raw))
    if not digits:
        return None
    return int(digits)


def _item_to_row(item: ET.Element, district: str) -> Dict:
    row = {key: _xml_text(item, names) for key, names in ITEM_FIELDS.items()}
    row["구"] = district
    price = _parse_price_manwon(row.get("거래금액", ""))
    row["거래금액_만원"] = price
    area = row.get("전용면적") or ""
    try:
        row["평"] = round(float(area) / 3.3058, 1) if area else None
    except ValueError:
        row["평"] = None
    y, m, d = row.get("년", ""), row.get("월", ""), row.get("일", "")
    if y and m and d:
        row["계약일"] = f"{int(y):04d}-{int(m):02d}-{int(d):02d}"
    else:
        row["계약일"] = ""
    return row


class MolitTradeClient:
    def __init__(self):
        self.service_key = molit_api_key()
        self.base_url: Optional[str] = None
        self.session = requests.Session()

    def _request(self, url: str, lawd_cd: str, deal_ymd: str, page_no: int, num_of_rows: int = 1000) -> ET.Element:
        params = {
            "serviceKey": self.service_key,
            "LAWD_CD": lawd_cd,
            "DEAL_YMD": deal_ymd,
            "pageNo": str(page_no),
            "numOfRows": str(num_of_rows),
        }
        last_err = None
        for attempt in range(MAX_RETRIES):
            try:
                resp = self.session.get(url, params=params, timeout=30)
                resp.raise_for_status()
                root = ET.fromstring(resp.content)
                auth_msg = _find_text(root, "returnAuthMsg") or _find_text(root, "errMsg")
                if auth_msg and "NORMAL" not in auth_msg.upper():
                    raise RuntimeError(auth_msg)
                return root
            except (requests.RequestException, ET.ParseError) as exc:
                last_err = exc
                time.sleep(0.8 * (attempt + 1))
        raise RuntimeError(f"API 요청 실패: {type(last_err).__name__}")

    def _pick_working_url(self, lawd_cd: str, deal_ymd: str) -> str:
        if self.base_url:
            return self.base_url
        errors = []
        for url in TRADE_API_URLS:
            try:
                root = self._request(url, lawd_cd, deal_ymd, 1, 10)
                code = _find_text(root, "resultCode")
                msg = _find_text(root, "resultMsg")
                if code in ("00", "000", "03", "0000") or (not code and root.find(".//item") is not None):
                    self.base_url = url
                    return url
                errors.append(f"{msg or code or 'unknown'}")
            except Exception as exc:
                errors.append(type(exc).__name__)
        raise RuntimeError("국토부 실거래 API에 연결하지 못했습니다. " + "; ".join(errors[:3]))

    def fetch_month(self, lawd_cd: str, deal_ymd: str) -> List[ET.Element]:
        url = self._pick_working_url(lawd_cd, deal_ymd)
        items: List[ET.Element] = []
        page = 1
        total = None
        while True:
            root = self._request(url, lawd_cd, deal_ymd, page)
            code = _find_text(root, "resultCode")
            msg = _find_text(root, "resultMsg")
            if code in ("03",):
                break
            if code and code not in ("00", "000", "0000"):
                raise RuntimeError(msg or f"API 오류 코드 {code}")
            page_items = root.findall(".//item")
            items.extend(page_items)
            if total is None:
                total_raw = _find_text(root, "totalCount")
                total = int(total_raw) if total_raw.isdigit() else len(page_items)
            if not page_items or len(items) >= total:
                break
            page += 1
            time.sleep(MOLIT_REQUEST_DELAY)
        return items


def load_tracked_districts(path: str = TRACKED_DISTRICTS_CSV) -> List[str]:
    from sheets_store import is_sheets_configured, load_districts

    if is_sheets_configured():
        districts = load_districts()
    else:
        districts = []
        if os.path.exists(path):
            df = pd.read_csv(path, encoding="utf-8-sig")
            if "구" in df.columns:
                districts = [str(x).strip() for x in df["구"].dropna().tolist() if str(x).strip()]
        elif os.path.exists(TRACKED_COMPLEXES_CSV):
            old = pd.read_csv(TRACKED_COMPLEXES_CSV, encoding="utf-8-sig")
            if "구" in old.columns:
                districts = [str(x).strip() for x in old["구"].dropna().unique().tolist() if str(x).strip()]
    unique = []
    for name in districts:
        if name in SEOUL_LAWD_CD and name not in unique:
            unique.append(name)
    return unique


def save_tracked_districts(districts: Sequence[str], path: str = TRACKED_DISTRICTS_CSV) -> None:
    unique = []
    for name in districts:
        name = str(name).strip()
        if name in SEOUL_LAWD_CD and name not in unique:
            unique.append(name)
    from sheets_store import is_sheets_configured, save_districts

    if is_sheets_configured():
        save_districts(unique)
        return
    pd.DataFrame({"구": unique}).to_csv(path, index=False, encoding="utf-8-sig")


def load_trade_history(path: str = TRADE_HISTORY_CSV) -> pd.DataFrame:
    from sheets_store import is_sheets_configured, load_trades

    if is_sheets_configured():
        try:
            return load_trades()
        except Exception:
            return pd.DataFrame()
    if not os.path.exists(path):
        return pd.DataFrame()
    try:
        return pd.read_csv(path, encoding="utf-8-sig")
    except Exception:
        return pd.DataFrame()


def save_trade_history(df: pd.DataFrame, path: str = TRADE_HISTORY_CSV) -> None:
    from sheets_store import is_sheets_configured, save_trades

    if is_sheets_configured():
        save_trades(df)
        return
    df.to_csv(path, index=False, encoding="utf-8-sig")


def district_month_days(df: pd.DataFrame) -> Dict[Tuple[str, str], Set[int]]:
    """시트/CSV의 (구, YYYYMM)별 계약 일자 집합."""
    if df is None or df.empty or "구" not in df.columns:
        return {}
    y = m = d = None
    if all(c in df.columns for c in ("년", "월", "일")):
        y = pd.to_numeric(df["년"], errors="coerce")
        m = pd.to_numeric(df["월"], errors="coerce")
        d = pd.to_numeric(df["일"], errors="coerce")
    if (y is None or y.isna().all()) and "계약일" in df.columns:
        dt = pd.to_datetime(df["계약일"], errors="coerce")
        y, m, d = dt.dt.year, dt.dt.month, dt.dt.day
    if y is None:
        return {}
    work = pd.DataFrame(
        {
            "구": df["구"].astype(str).str.strip(),
            "_y": y,
            "_m": m,
            "_d": d,
        }
    ).dropna()
    if work.empty:
        return {}
    work["_ym"] = work["_y"].astype(int).map("{:04d}".format) + work["_m"].astype(int).map("{:02d}".format)
    out: Dict[Tuple[str, str], Set[int]] = {}
    for (gu, ym), part in work.groupby(["구", "_ym"], sort=False):
        out[(str(gu), str(ym))] = set(int(x) for x in part["_d"].tolist())
    return out


def is_month_span_complete(days: Set[int], ym: str) -> bool:
    """해당 월 데이터가 1일부터 말일까지 걸쳐 있으면 True."""
    if not days or not ym or len(ym) != 6:
        return False
    last = calendar.monthrange(int(ym[:4]), int(ym[4:]))[1]
    return min(days) == 1 and max(days) == last


def _dedupe_trades(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    keys = [c for c in ["구", "아파트명", "지번", "계약일", "층", "전용면적", "거래금액_만원"] if c in df.columns]
    if not keys:
        return df.drop_duplicates()
    return df.drop_duplicates(subset=keys, keep="last")


def _merge_rows(existing: pd.DataFrame, new_rows: List[Dict]) -> pd.DataFrame:
    new_df = pd.DataFrame(new_rows)
    merged = pd.concat([existing, new_df], ignore_index=True) if not existing.empty else new_df
    if merged.empty:
        return merged
    merged = _dedupe_trades(merged)
    if "계약일" in merged.columns:
        merged = merged.sort_values(["계약일", "구", "아파트명"], ascending=[False, True, True], na_position="last")
    return merged


def collect_trades(
    districts: Optional[Sequence[str]] = None,
    start_ym: str = MOLIT_TRADE_START_YM,
    end_ym: Optional[str] = None,
    on_progress: Optional[ProgressFn] = None,
    skip_complete_months: bool = True,
) -> pd.DataFrame:
    if not has_molit_api_key():
        raise RuntimeError("PUBLIC_DATA_API_KEY가 없습니다. secrets.toml에 Decoding/Encoding 키를 저장하세요.")

    if districts is None:
        district_list = load_tracked_districts()
    else:
        district_list = [str(x).strip() for x in districts if str(x).strip()]
        unique = []
        for name in district_list:
            if name not in unique:
                unique.append(name)
        district_list = unique

    if not district_list:
        raise RuntimeError("추적할 구를 먼저 등록하세요.")

    missing = [d for d in district_list if d not in SEOUL_LAWD_CD]
    if missing:
        raise RuntimeError(f"법정동코드를 모르는 자치구입니다: {', '.join(missing)}")

    end_ym = end_ym or current_ym()
    months = month_range(start_ym, end_ym)
    client = MolitTradeClient()
    buffer: List[Dict] = []
    existing = load_trade_history()
    jobs = [(d, ym) for d in district_list for ym in months]
    total = len(jobs)
    complete_days = district_month_days(existing) if skip_complete_months else {}

    for i, (district, ym) in enumerate(jobs, start=1):
        if skip_complete_months and is_month_span_complete(complete_days.get((district, ym), set()), ym):
            if on_progress:
                on_progress(i, total, f"{district} {ym[:4]}.{ym[4:]} 생략")
            continue
        if on_progress:
            on_progress(i - 1, total, f"{district} {ym[:4]}.{ym[4:]} 조회 중")
        items = client.fetch_month(SEOUL_LAWD_CD[district], ym)
        buffer.extend(_item_to_row(item, district) for item in items)
        time.sleep(MOLIT_REQUEST_DELAY)

    if not buffer:
        if on_progress:
            on_progress(total, total, "건너뛴 연월만 있어 저장하지 않습니다")
        return existing

    if on_progress:
        on_progress(total, total, "시트 저장 중...")
    merged = _merge_rows(existing, buffer)
    save_trade_history(merged)
    if on_progress:
        on_progress(total, total, f"저장 완료 ({len(merged)}건)")
    return merged
