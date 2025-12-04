"""
설정 파일
API 키는 .env 파일에 저장하세요. (보안상 권장)
또는 환경변수로 설정하거나, 아래에 직접 입력할 수 있습니다.
"""
import os
from dotenv import load_dotenv

# .env 파일 로드
load_dotenv()

# 공공데이터포털 API 키 (https://www.data.go.kr 에서 발급)
# 우선순위: 환경변수 > .env 파일 > 하드코딩된 값
PUBLIC_DATA_API_KEY = os.getenv("PUBLIC_DATA_API_KEY", "YOUR_PUBLIC_DATA_API_KEY")

# 서울 열린데이터광장 API 키 (https://data.seoul.go.kr 에서 발급)
# 우선순위: 환경변수 > .env 파일 > 하드코딩된 값
# .env 파일에 "SEOUL_DATA_API_KEY=your_api_key_here" 형식으로 추가하세요
SEOUL_DATA_API_KEY = os.getenv("SEOUL_DATA_API_KEY", "YOUR_SEOUL_API_KEY_HERE")

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

