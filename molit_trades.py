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
from datetime import date, datetime

from seoul_time import as_seoul_date, format_seoul_stamp, seoul_now, seoul_today
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
    now = seoul_now()
    return f"{now.year:04d}{now.month:02d}"


def months_back(n: int) -> str:
    now = seoul_now()
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
    now = seoul_now()
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
                if items:
                    raise RuntimeError("월별 조회가 중간에 종료되었습니다. 저장하지 않습니다.")
                break
            if code and code not in ("00", "000", "0000"):
                raise RuntimeError(msg or f"API 오류 코드 {code}")
            page_items = root.findall(".//item")
            items.extend(page_items)
            if total is None:
                total_raw = _find_text(root, "totalCount")
                if not total_raw.isdigit():
                    raise RuntimeError("API 응답의 전체 건수를 확인할 수 없어 저장하지 않습니다.")
                total = int(total_raw)
            if not page_items and len(items) < total:
                raise RuntimeError("API 페이지가 누락되어 저장하지 않습니다.")
            if len(items) >= total:
                if len(items) != total:
                    raise RuntimeError("API 전체 건수와 받은 건수가 달라 저장하지 않습니다.")
                break
            page += 1
            time.sleep(MOLIT_REQUEST_DELAY)
        return items


def load_district_meta(path: str = TRACKED_DISTRICTS_CSV) -> pd.DataFrame:
    from sheets_store import is_sheets_configured, load_district_meta as load_sheet_meta, normalize_district_meta

    if is_sheets_configured():
        return load_sheet_meta()
    if os.path.exists(path):
        return normalize_district_meta(pd.read_csv(path, encoding="utf-8-sig"))
    if os.path.exists(TRACKED_COMPLEXES_CSV):
        old = pd.read_csv(TRACKED_COMPLEXES_CSV, encoding="utf-8-sig")
        if "구" in old.columns:
            return normalize_district_meta(pd.DataFrame({"구": old["구"]}))
    return normalize_district_meta(pd.DataFrame())


def load_tracked_districts(path: str = TRACKED_DISTRICTS_CSV) -> List[str]:
    unique = []
    for name in load_district_meta(path)["구"].tolist():
        name = str(name).strip()
        if name in SEOUL_LAWD_CD and name not in unique:
            unique.append(name)
    return unique


def save_tracked_districts(districts: Sequence[str], path: str = TRACKED_DISTRICTS_CSV) -> None:
    unique = []
    for name in districts:
        name = str(name).strip()
        if name in SEOUL_LAWD_CD and name not in unique:
            unique.append(name)
    from sheets_store import is_sheets_configured, save_districts, DISTRICT_META_COLS

    if is_sheets_configured():
        save_districts(unique)
        return
    current = {str(row["구"]): row.to_dict() for _, row in load_district_meta(path).iterrows()}
    rows = []
    for name in unique:
        row = current.get(name, {col: "" for col in DISTRICT_META_COLS})
        row["구"] = name
        rows.append({col: row.get(col, "") for col in DISTRICT_META_COLS})
    pd.DataFrame(rows, columns=DISTRICT_META_COLS).to_csv(path, index=False, encoding="utf-8-sig")


def stamp_reg_dt(rows: Sequence[Dict], when: Optional[datetime] = None) -> List[Dict]:
    stamp = format_seoul_stamp(when)
    stamped = []
    for row in rows:
        item = dict(row)
        item["REG_DT"] = stamp
        stamped.append(item)
    return stamped


def last_reg_date(district: str, meta: Optional[pd.DataFrame] = None):
    frame = load_district_meta() if meta is None else meta
    if frame is None or frame.empty or "구" not in frame.columns or "LAST_REG_DT" not in frame.columns:
        return None
    dates = [as_seoul_date(value) for value in frame.loc[frame["구"].astype(str).str.strip() == district, "LAST_REG_DT"]]
    dates = [value for value in dates if value is not None]
    return max(dates) if dates else None


def districts_needing_today_refresh(
    districts: Sequence[str],
    today: Optional[date] = None,
    meta: Optional[pd.DataFrame] = None,
) -> List[str]:
    today = today or seoul_today()
    frame = load_district_meta() if meta is None else meta
    return [name for name in districts if last_reg_date(name, frame) != today]


def auto_update_districts(meta: Optional[pd.DataFrame] = None) -> List[str]:
    from sheets_store import auto_update_enabled

    frame = load_district_meta() if meta is None else meta
    if frame is None or frame.empty or "구" not in frame.columns:
        return []
    names = []
    for _, row in frame.iterrows():
        name = str(row.get("구", "")).strip()
        if name and auto_update_enabled(row.get("자동업데이트", "")):
            names.append(name)
    return names


def next_ym(year_month: str) -> str:
    year, month = int(year_month[:4]), int(year_month[4:6])
    month += 1
    if month > 12:
        year, month = year + 1, 1
    return f"{year:04d}{month:02d}"


def prev_ym(year_month: str) -> str:
    year, month = int(year_month[:4]), int(year_month[4:6])
    month -= 1
    if month < 1:
        year, month = year - 1, 12
    return f"{year:04d}{month:02d}"


def is_closed_month(year_month: str, collected_at) -> bool:
    ym = str(year_month or "").replace("-", "")[:6]
    if len(ym) < 6 or collected_at in (None, "") or pd.isna(collected_at):
        return False
    try:
        stamp = pd.Timestamp(collected_at)
        next_month = pd.Timestamp(f"{ym[:4]}-{ym[4:6]}-01") + pd.offsets.MonthBegin(1)
    except (ValueError, TypeError):
        return False
    return stamp >= next_month


def extend_completed_range(start: str, end: str, year_month: str) -> Tuple[str, str]:
    start, end = str(start or "").replace("-", "")[:6], str(end or "").replace("-", "")[:6]
    ym = str(year_month or "").replace("-", "")[:6]
    if len(ym) < 6:
        return start, end
    if len(start) < 6 or len(end) < 6:
        return ym, ym
    if start <= ym <= end:
        return start, end
    if ym == next_ym(end):
        return start, ym
    if ym == prev_ym(start):
        return ym, end
    return start, end


def completed_months(meta: Optional[pd.DataFrame] = None) -> Set[Tuple[str, str]]:
    frame = meta if meta is not None else load_district_meta()
    complete: Set[Tuple[str, str]] = set()
    if frame is None or frame.empty:
        return complete
    for _, row in frame.iterrows():
        district = str(row.get("구", "")).strip()
        start = str(row.get("완료시작연월") or "").replace("-", "")[:6]
        end = str(row.get("완료종료연월") or "").replace("-", "")[:6]
        if not district or len(start) < 6 or len(end) < 6:
            continue
        for ym in month_range(start, end):
            complete.add((district, ym))
    return complete


def trade_date_bounds(df: pd.DataFrame, district: str) -> Tuple[str, str]:
    if df is None or df.empty or "구" not in df.columns or "계약일" not in df.columns:
        return "", ""
    dates = pd.to_datetime(df.loc[df["구"].astype(str).str.strip() == district, "계약일"], errors="coerce").dropna()
    if dates.empty:
        return "", ""
    return dates.min().strftime("%Y-%m-%d"), dates.max().strftime("%Y-%m-%d")


def update_district_meta_from_trades(
    districts: Sequence[str],
    trades: pd.DataFrame,
    stamp: Optional[str] = None,
    completed_ranges: Optional[Dict[str, Tuple[str, str]]] = None,
) -> None:
    from sheets_store import DISTRICT_META_COLS, is_sheets_configured, update_district_meta

    stamp = stamp or format_seoul_stamp()
    updates = {}
    for name in districts:
        first, last = trade_date_bounds(trades, name)
        payload = {"LAST_REG_DT": stamp}
        if first:
            payload["최초 거래일"] = first
        if last:
            payload["최종 거래일"] = last
        start_end = (completed_ranges or {}).get(name)
        if start_end:
            start, end = start_end
            if start:
                payload["완료시작연월"] = start
            if end:
                payload["완료종료연월"] = end
        updates[name] = payload
    if is_sheets_configured():
        update_district_meta(updates, order=list(districts))
        return
    current = {str(row["구"]): row.to_dict() for _, row in load_district_meta().iterrows()}
    names = list(dict.fromkeys(list(districts) + list(current)))
    rows = []
    for name in names:
        row = current.get(name, {col: "" for col in DISTRICT_META_COLS})
        row["구"] = name
        for key, value in updates.get(name, {}).items():
            if value not in (None, ""):
                row[key] = value
        rows.append({col: row.get(col, "") for col in DISTRICT_META_COLS})
    pd.DataFrame(rows, columns=DISTRICT_META_COLS).to_csv(TRACKED_DISTRICTS_CSV, index=False, encoding="utf-8-sig")


def load_trade_history(path: str = TRADE_HISTORY_CSV) -> pd.DataFrame:
    from sheets_store import is_sheets_configured, load_trades

    if is_sheets_configured():
        return load_trades()
    if not os.path.exists(path):
        return pd.DataFrame()
    return pd.read_csv(path, encoding="utf-8-sig")


def save_trade_history(
    df: pd.DataFrame,
    path: str = TRADE_HISTORY_CSV,
    districts: Optional[Sequence[str]] = None,
) -> None:
    from sheets_store import is_sheets_configured, save_trades

    if is_sheets_configured():
        save_trades(df, districts=list(districts) if districts is not None else None)
        return
    df.to_csv(path, index=False, encoding="utf-8-sig")


def replace_collected_months(existing, rows, jobs):
    """Replace only successfully fetched months; preserve identical real transactions."""
    if existing.empty:
        kept = existing
    else:
        dates = pd.to_datetime(existing["계약일"], errors="coerce")
        keys = list(zip(existing["구"].astype(str), dates.dt.strftime("%Y%m")))
        kept = existing.loc[[key not in jobs for key in keys]]
    fresh = pd.DataFrame(rows)
    merged = pd.concat([kept, fresh], ignore_index=True)
    if not merged.empty:
        merged = merged.sort_values(["계약일", "구", "아파트명"], ascending=[False, True, True])
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
    meta = load_district_meta()
    complete = completed_months(meta) if skip_complete_months else set()
    fetched = set()

    for i, (district, ym) in enumerate(jobs, start=1):
        if (district, ym) in complete:
            if on_progress:
                on_progress(i, total, f"{district} {ym[:4]}.{ym[4:]} 생략")
            continue
        month_label = f"{district} {ym[:4]}.{ym[4:]}"
        if on_progress:
            on_progress(i - 1, total, f"{month_label} 업데이트 중")
        items = client.fetch_month(SEOUL_LAWD_CD[district], ym)
        buffer.extend(_item_to_row(item, district) for item in items)
        fetched.add((district, ym))
        if on_progress:
            on_progress(i, total, f"{month_label} 업데이트 완료 ({len(items)}건)")
        time.sleep(MOLIT_REQUEST_DELAY)

    if not fetched:
        if on_progress:
            on_progress(total, total, "건너뛴 연월만 있어 저장하지 않습니다")
        return existing

    if on_progress:
        on_progress(total, total, "시트 저장 중...")
    stamp = format_seoul_stamp()
    merged = replace_collected_months(existing, stamp_reg_dt(buffer), fetched)
    changed = sorted({district for district, _ in fetched})
    save_trade_history(merged, districts=changed)
    # Mark completion only after the data write succeeds. Failure here causes a safe refetch.
    current = {str(row["구"]): row.to_dict() for _, row in meta.iterrows()} if meta is not None and not meta.empty else {}
    completed_ranges: Dict[str, Tuple[str, str]] = {}
    for name in changed:
        row = current.get(name, {})
        start = str(row.get("완료시작연월") or "")
        end = str(row.get("완료종료연월") or "")
        for district, ym in sorted(fetched):
            if district != name:
                continue
            if is_closed_month(ym, stamp):
                start, end = extend_completed_range(start, end, ym)
        if start and end:
            completed_ranges[name] = (start, end)
    update_district_meta_from_trades(changed, merged, stamp=stamp, completed_ranges=completed_ranges)
    merged.attrs["collected_count"] = len(buffer)
    if on_progress:
        on_progress(total, total, f"저장 완료 ({len(merged)}건)")
    return merged
