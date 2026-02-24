"""
설정 파일
API 키는 .env 파일에 저장하세요. (보안상 권장)
또는 환경변수로 설정하거나, 아래에 직접 입력할 수 있습니다.
Streamlit Cloud에서는 Secrets를 사용할 수 있습니다.
"""
import os
from dotenv import load_dotenv

# Streamlit Secrets 지원 (Streamlit Cloud용)
try:
    import streamlit as st
    USE_STREAMLIT_SECRETS = True
except ImportError:
    USE_STREAMLIT_SECRETS = False

# .env 파일 로드
load_dotenv()

def get_secret(key: str, default: str = None) -> str:
    """Secrets 또는 환경변수에서 값을 가져옵니다.
    우선순위: Streamlit Secrets > 환경변수 > .env 파일 > 기본값
    Cloud Secrets: [secrets] 섹션 사용 시 st.secrets["secrets"][key]에 위치
    """
    if USE_STREAMLIT_SECRETS:
        try:
            if hasattr(st, "secrets") and st.secrets:
                # 1) [secrets] 섹션 하위 (Cloud에서 [secrets] 붙여넣은 경우)
                try:
                    val = st.secrets["secrets"][key]
                    if val is not None:
                        return str(val).strip()
                except (KeyError, TypeError, AttributeError):
                    pass
                # 2) 최상위 키
                try:
                    val = st.secrets[key]
                    if val is not None:
                        return str(val).strip()
                except (KeyError, TypeError):
                    pass
        except Exception:
            pass

    value = os.getenv(key)
    if value:
        return value
    return default

# 공공데이터포털 API 키 (https://www.data.go.kr 에서 발급)
PUBLIC_DATA_API_KEY = get_secret("PUBLIC_DATA_API_KEY", "YOUR_PUBLIC_DATA_API_KEY")

# 서울 열린데이터광장 API 키 (https://data.seoul.go.kr 에서 발급)
SEOUL_DATA_API_KEY = get_secret("SEOUL_DATA_API_KEY", "YOUR_SEOUL_API_KEY_HERE")

# 서울 열린데이터광장 데이터셋 ID
SEOUL_REAL_ESTATE_DATASET_ID = "OA-21275"  # 부동산 실거래가
SEOUL_APARTMENT_INFO_DATASET_ID = "OA-15818"  # 공동주택 아파트 정보 (메타데이터)

# 서울시 자치구 목록
SEOUL_DISTRICTS = [
    "강남구", "강동구", "강북구", "강서구", "관악구", "광진구", "구로구", "금천구",
    "노원구", "도봉구", "동대문구", "동작구", "마포구", "서대문구", "서초구", "성동구",
    "성북구", "송파구", "양천구", "영등포구", "용산구", "은평구", "종로구", "중구", "중랑구"
]

# 크롤링 설정
CRAWL_DELAY = 1  # 요청 간 지연 시간 (초)
MAX_RETRIES = 3  # 최대 재시도 횟수

