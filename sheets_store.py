"""
비공개 Google 스프레드시트 저장소.

시트는 '링크가 있는 모든 사용자'가 아니라,
본인 구글 계정 + 서비스 계정 이메일에만 공유해야 합니다.
"""
from __future__ import annotations

import time
from datetime import date
from typing import Any, Callable, Dict, List, Optional

import pandas as pd

SHEET_TRADES = "trades"
SHEET_DISTRICTS = "districts"
SHEET_COLLECTION_LOG = "collection_log"
REG_DT_COL = "REG_DT"
DISTRICT_META_COLS = ["구", "LAST_REG_DT", "최초 거래일", "최종 거래일"]
RESERVED_SHEETS = frozenset({SHEET_TRADES, SHEET_DISTRICTS, SHEET_COLLECTION_LOG})


def _secrets():
    try:
        import streamlit as st
        return getattr(st, "secrets", None)
    except Exception:
        return None


def _section(*names: str) -> Optional[Any]:
    secrets = _secrets()
    if not secrets:
        return None
    for name in names:
        try:
            val = secrets["secrets"][name]
            if val is not None:
                return val
        except (KeyError, TypeError, AttributeError):
            pass
        try:
            val = secrets[name]
            if val is not None:
                return val
        except (KeyError, TypeError, AttributeError):
            pass
    return None


def spreadsheet_id() -> str:
    sheets = _section("sheets")
    if sheets is not None:
        try:
            sid = sheets["spreadsheet_id"]
            if sid:
                return str(sid).strip()
        except (KeyError, TypeError):
            pass
    raw = _section("GOOGLE_SHEET_ID")
    if raw:
        return str(raw).strip()
    return ""


def _service_account_info() -> Dict[str, Any]:
    raw = _section("gcp_service_account")
    if not raw:
        return {}
    try:
        info = dict(raw)
    except Exception:
        return {}
    key = info.get("private_key")
    if key:
        info["private_key"] = str(key).replace("\\n", "\n")
    return info


def is_sheets_configured() -> bool:
    info = _service_account_info()
    return bool(spreadsheet_id() and info.get("client_email") and info.get("private_key"))


def _with_sheets_retry(fn: Callable, retries: int = 6):
    last = None
    for i in range(retries):
        try:
            return fn()
        except Exception as exc:
            last = exc
            text = str(exc)
            if "429" not in text and "Quota exceeded" not in text:
                raise
            if i < retries - 1:
                time.sleep(min(60, 10 * (i + 1)))
    raise RuntimeError("Google Sheets 분당 호출 한도를 넘었습니다. 1분 뒤 다시 시도하세요.") from last


def _client():
    import gspread
    from google.oauth2.service_account import Credentials

    info = _service_account_info()
    if not info:
        raise RuntimeError("secrets.toml에 [gcp_service_account]가 없습니다.")
    scopes = (
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    )
    creds = Credentials.from_service_account_info(info, scopes=scopes)
    return gspread.authorize(creds)


def _spreadsheet():
    sid = spreadsheet_id()
    if not sid:
        raise RuntimeError("secrets.toml에 sheets.spreadsheet_id 또는 GOOGLE_SHEET_ID가 없습니다.")
    return _with_sheets_retry(lambda: _client().open_by_key(sid))


def spreadsheet_url() -> str:
    sid = spreadsheet_id()
    if not sid:
        return ""
    return f"https://docs.google.com/spreadsheets/d/{sid}/edit"


def _worksheet(title: str, cols: int = 20):
    from gspread.exceptions import WorksheetNotFound

    book = _spreadsheet()

    def _get():
        try:
            return book.worksheet(title)
        except WorksheetNotFound:
            return book.add_worksheet(title=title, rows=2000, cols=max(cols, 8))

    return _with_sheets_retry(_get)


def _read_df(title: str) -> pd.DataFrame:
    ws = _worksheet(title)
    values = _with_sheets_retry(ws.get_all_values)
    if not values or len(values) < 2:
        if values and values[0]:
            return pd.DataFrame(columns=values[0])
        return pd.DataFrame()
    header = values[0]
    rows = values[1:]
    df = pd.DataFrame(rows, columns=header)
    return df.replace("", pd.NA)


def _write_df(title: str, df: pd.DataFrame) -> None:
    if df is None:
        df = pd.DataFrame()
    out = df.copy()
    ws = _worksheet(title, cols=max(len(out.columns) + 2, 8) if len(out.columns) else 8)
    if out.empty and len(out.columns) == 0:
        _with_sheets_retry(ws.clear)
        return
    out = out.fillna("")
    header = [str(c) for c in out.columns.tolist()]
    values = [header] + out.astype(str).values.tolist()
    needed_rows = max(len(values) + 10, 100)
    needed_cols = max(len(header) + 2, 8)

    # Grow before writing, but never clear or shrink existing data first.
    # A failed update leaves the previous values intact.
    if needed_rows > ws.row_count or needed_cols > ws.col_count:
        _with_sheets_retry(lambda: ws.resize(
            rows=max(needed_rows, ws.row_count), cols=max(needed_cols, ws.col_count)
        ))
    _with_sheets_retry(lambda: ws.update(
        range_name="A1", values=values, value_input_option="RAW"
    ))
    # Only remove stale trailing cells after the new values have been accepted.
    if len(values) < ws.row_count:
        _with_sheets_retry(lambda: ws.batch_clear([f"{len(values) + 1}:{ws.row_count}"]))
    if len(header) < ws.col_count:
        from gspread.utils import rowcol_to_a1
        first = rowcol_to_a1(1, len(header) + 1)
        last = rowcol_to_a1(len(values), ws.col_count)
        _with_sheets_retry(lambda: ws.batch_clear([f"{first}:{last}"]))


def _normalize_trades(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return df if df is not None else pd.DataFrame()
    out = df.copy()
    if "거래금액_만원" in out.columns:
        out["거래금액_만원"] = pd.to_numeric(out["거래금액_만원"], errors="coerce")
    if "평" in out.columns:
        out["평"] = pd.to_numeric(out["평"], errors="coerce")
    return _move_reg_dt_last(out)


def _move_reg_dt_last(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty or REG_DT_COL not in df.columns:
        return df
    cols = [c for c in df.columns if c != REG_DT_COL] + [REG_DT_COL]
    return df[cols]


def _district_sheet_names() -> List[str]:
    from config import SEOUL_LAWD_CD

    names = []
    try:
        titles = [ws.title for ws in _spreadsheet().worksheets()]
    except Exception:
        titles = []
    for title in titles:
        if title in SEOUL_LAWD_CD and title not in names:
            names.append(title)
    if SHEET_TRADES in titles:
        names = [SHEET_TRADES] + [name for name in names if name != SHEET_TRADES]
    for district in load_districts():
        if district not in names:
            names.append(district)
    return names


def empty_district_meta() -> pd.DataFrame:
    return pd.DataFrame(columns=DISTRICT_META_COLS)


def normalize_district_meta(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return empty_district_meta()
    out = df.copy()
    if "구" not in out.columns:
        return empty_district_meta()
    for col in DISTRICT_META_COLS:
        if col not in out.columns:
            out[col] = pd.NA
    out["구"] = out["구"].astype(str).str.strip()
    out = out.loc[out["구"].ne("") & ~out["구"].isin(["nan", "None", "<NA>"])]
    return out[DISTRICT_META_COLS].drop_duplicates("구", keep="last").reset_index(drop=True)


def load_district_meta() -> pd.DataFrame:
    return normalize_district_meta(_read_df(SHEET_DISTRICTS))


def save_district_meta(df: pd.DataFrame) -> None:
    _write_df(SHEET_DISTRICTS, normalize_district_meta(df))


def last_reg_dates(meta: Optional[pd.DataFrame] = None) -> Dict[str, date]:
    from seoul_time import as_seoul_date

    frame = normalize_district_meta(meta) if meta is not None else load_district_meta()
    dates: Dict[str, date] = {}
    if frame.empty:
        return dates
    for name, value in zip(frame["구"], frame["LAST_REG_DT"]):
        parsed = as_seoul_date(value)
        if parsed is not None:
            dates[str(name)] = parsed
    return dates


def last_reg_date(district: str, meta: Optional[pd.DataFrame] = None):
    return last_reg_dates(meta).get(district)


def update_district_meta(updates: Dict[str, Dict[str, Any]], order: Optional[List[str]] = None) -> None:
    meta = load_district_meta()
    names = list(order or [])
    for name in list(updates) + [str(x) for x in meta["구"].tolist()]:
        if name and name not in names:
            names.append(name)
    rows = []
    current = {str(row["구"]): row.to_dict() for _, row in meta.iterrows()}
    for name in names:
        row = current.get(name, {col: "" for col in DISTRICT_META_COLS})
        row["구"] = name
        for key, value in updates.get(name, {}).items():
            if key in DISTRICT_META_COLS and key != "구" and value not in (None, ""):
                row[key] = value
        rows.append({col: row.get(col, "") for col in DISTRICT_META_COLS})
    save_district_meta(pd.DataFrame(rows, columns=DISTRICT_META_COLS))


def load_trades() -> pd.DataFrame:
    frames = [_normalize_trades(_read_df(title)) for title in _district_sheet_names()]
    frames = [f for f in frames if f is not None and not f.empty]
    if not frames:
        return pd.DataFrame()
    out = pd.concat(frames, ignore_index=True)
    subset = [c for c in ["구", "계약일", "아파트명", "지번", "층", "전용면적", "거래금액_만원"] if c in out.columns]
    if subset:
        out = out.drop_duplicates(subset, keep="last")
    return out.reset_index(drop=True)


def save_trades(df: pd.DataFrame, districts: Optional[List[str]] = None) -> None:
    if df is None:
        df = pd.DataFrame()
    if districts:
        if df.empty or "구" not in df.columns:
            return
        groups = df.copy()
        groups["_sheet"] = groups["구"].astype(str).str.strip()
        for name in districts:
            part = groups.loc[groups["_sheet"] == name].drop(columns=["_sheet"])
            _write_df(name, _move_reg_dt_last(part))
        return
    if df.empty or "구" not in df.columns:
        _write_df(SHEET_TRADES, _move_reg_dt_last(df))
        return
    groups = df.copy()
    groups["_sheet"] = groups["구"].astype(str).str.strip()
    targets = [x for x in groups["_sheet"].dropna().unique().tolist() if x]
    for name in targets:
        part = groups.loc[groups["_sheet"] == name].drop(columns=["_sheet"])
        _write_df(name, _move_reg_dt_last(part))


def load_districts() -> List[str]:
    return [str(x).strip() for x in load_district_meta()["구"].tolist() if str(x).strip()]


def save_districts(districts: List[str]) -> None:
    update_district_meta({}, order=list(districts))
