"""
비공개 Google 스프레드시트 저장소.

시트는 '링크가 있는 모든 사용자'가 아니라,
본인 구글 계정 + 서비스 계정 이메일에만 공유해야 합니다.
"""
from __future__ import annotations

import time
from typing import Any, Callable, Dict, List, Optional

import pandas as pd

SHEET_TRADES = "trades"
SHEET_DISTRICTS = "districts"


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
            time.sleep(min(65, 10 * (i + 1)))
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
    book = _spreadsheet()

    def _get():
        try:
            return book.worksheet(title)
        except Exception:
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

    def _put():
        try:
            ws.resize(rows=needed_rows, cols=needed_cols)
        except Exception:
            pass
        ws.clear()
        ws.update(range_name="A1", values=values, value_input_option="USER_ENTERED")

    _with_sheets_retry(_put)


def load_trades() -> pd.DataFrame:
    df = _read_df(SHEET_TRADES)
    if df.empty:
        return df
    if "거래금액_만원" in df.columns:
        df["거래금액_만원"] = pd.to_numeric(df["거래금액_만원"], errors="coerce")
    if "평" in df.columns:
        df["평"] = pd.to_numeric(df["평"], errors="coerce")
    return df


def save_trades(df: pd.DataFrame) -> None:
    _write_df(SHEET_TRADES, df)


def load_districts() -> List[str]:
    df = _read_df(SHEET_DISTRICTS)
    if df.empty or "구" not in df.columns:
        return []
    return [str(x).strip() for x in df["구"].dropna().tolist() if str(x).strip()]


def save_districts(districts: List[str]) -> None:
    _write_df(SHEET_DISTRICTS, pd.DataFrame({"구": list(districts)}))
