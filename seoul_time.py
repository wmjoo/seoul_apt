"""서버가 UTC여도 수집 시각·일자 비교는 서울 달력을 쓴다."""
from datetime import date, datetime
from zoneinfo import ZoneInfo

import pandas as pd

SEOUL_TZ = ZoneInfo("Asia/Seoul")


def seoul_now(when: datetime | None = None) -> datetime:
    if when is None:
        return datetime.now(SEOUL_TZ)
    if when.tzinfo is None:
        return when.replace(tzinfo=SEOUL_TZ)
    return when.astimezone(SEOUL_TZ)


def seoul_today(when: datetime | None = None) -> date:
    return seoul_now(when).date()


def format_seoul_stamp(when: datetime | None = None) -> str:
    """서울 벽시계를 timezone 없는 문자열로 저장한다. 읽을 때도 서울 날짜로 해석한다."""
    return seoul_now(when).strftime("%Y-%m-%d %H:%M:%S")


def as_seoul_date(value) -> date | None:
    """tz-aware 값은 서울로 변환하고, naive 값은 이미 서울 벽시계로 본다."""
    ts = pd.to_datetime(value, errors="coerce")
    if pd.isna(ts):
        return None
    if getattr(ts, "tz", None) is None:
        ts = ts.tz_localize(SEOUL_TZ)
    else:
        ts = ts.tz_convert(SEOUL_TZ)
    return ts.date()
