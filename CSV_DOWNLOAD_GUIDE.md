# CSV 파일 다운로드 가이드

서울 열린데이터광장의 데이터셋은 Open API 또는 CSV 파일 다운로드를 제공합니다.

## 📋 데이터셋 구분

### 1. 서울시 공동주택 아파트 정보 (OA-15818) - 메타데이터
**용도**: 아파트 기본 정보 (아파트명, 주소, 준공일자, 세대수, 세대타입 등)
- **데이터셋 페이지**: https://data.seoul.go.kr/dataList/OA-15818/S/1/datasetView.do
- **포함 정보**: 아파트명, 주소, 홈페이지, 연면적, 관리비부과면적, 세대타입, 난방방식, 건설사, 시행사, 준공일자 등

### 2. 서울시 부동산 실거래가 정보 (OA-21275) - 실거래가
**용도**: 부동산 실거래가 정보 (실거래가, 보증금, 월세 등)
- **데이터셋 페이지**: https://data.seoul.go.kr/dataList/OA-21275/S/1/datasetView.do
- **포함 정보**: 자치구, 법정동, 신고년도, 대지권면적, 관리구분, 건물면적, 건물주용도, 물건금액, 지번코드, 건축년도 등

## 서울시 공동주택 아파트 정보 (OA-15818) - 메타데이터

### 다운로드 방법

1. **데이터셋 페이지 접속**
   - https://data.seoul.go.kr/dataList/OA-15818/A/1/datasetView.do

2. **CSV 파일 다운로드**
   - 페이지에서 "파일내려받기" 또는 "CSV 다운로드" 버튼 클릭
   - 또는 미리보기에서 "CSV 다운로드" 선택

3. **데이터 로드 및 처리**
   ```python
   from crawler import SeoulApartmentCrawler
   
   crawler = SeoulApartmentCrawler()
   
   # CSV 파일 로드
   df = crawler.load_seoul_csv_file("다운로드한_파일.csv")
   
   # 데이터 변환
   processed_df = crawler.process_seoul_apartment_info_data(df)
   
   # 저장
   crawler.save_to_csv(processed_df, "seoul_apartments.csv")
   ```

## 서울시 부동산 실거래가 정보 (OA-21275) - 실거래가

### 다운로드 방법

1. **데이터셋 페이지 접속**
   - https://data.seoul.go.kr/dataList/OA-21275/S/1/datasetView.do

2. **CSV 파일 다운로드**
   - 페이지에서 "파일내려받기" 또는 "CSV 다운로드" 버튼 클릭
   - 연도별로 필터링하여 다운로드 가능
   - 미리보기에서 필드명 "신고년도"로 필터 선택 후 연도별로 조회 및 다운로드

3. **데이터 로드 및 처리**
   ```python
   from crawler import SeoulApartmentCrawler
   
   crawler = SeoulApartmentCrawler()
   
   # CSV 파일 로드
   df = crawler.load_seoul_csv_file("다운로드한_실거래가_파일.csv")
   
   # 데이터 변환
   processed_df = crawler.process_seoul_real_estate_data(df)
   
   # 저장
   crawler.save_to_csv(processed_df, "seoul_real_estate.csv")
   ```

## 데이터 통합 사용 예시

두 데이터셋을 함께 사용하여 더 풍부한 정보를 얻을 수 있습니다:

```python
from crawler import SeoulApartmentCrawler
import pandas as pd

crawler = SeoulApartmentCrawler()

# 1. 아파트 메타데이터 로드
metadata_df = crawler.load_seoul_csv_file("아파트_메타데이터.csv")
processed_metadata = crawler.process_seoul_apartment_info_data(metadata_df)

# 2. 실거래가 데이터 로드
real_estate_df = crawler.load_seoul_csv_file("실거래가_데이터.csv")
processed_real_estate = crawler.process_seoul_real_estate_data(real_estate_df)

# 3. 메타데이터를 메인으로 사용 (더 많은 정보 포함)
crawler.save_to_csv(processed_metadata, "seoul_apartments.csv")

# 4. 실거래가 데이터는 별도로 저장
crawler.save_to_csv(processed_real_estate, "seoul_real_estate.csv")
```

## Open API 서비스명 확인 방법

만약 Open API를 사용하고 싶다면:

1. **데이터셋 페이지 접속**
   - 해당 데이터셋 페이지로 이동

2. **Open API 탭 확인**
   - 페이지 상단의 "Open API" 탭 클릭
   - 또는 "API 정보" 섹션 확인

3. **서비스명 확인**
   - API 엔드포인트에서 서비스명 확인
   - 예: `http://openapi.seoul.go.kr:8088/{인증키}/json/{서비스명}/1/5`

4. **크롤러 코드 수정**
   - `crawler.py`의 `crawl_seoul_apartment_info()` 메서드에서
   - `service_name` 변수를 실제 서비스명으로 변경

## 주의사항

- 일부 데이터셋은 Open API를 제공하지 않을 수 있습니다
- CSV 파일 다운로드가 더 안정적일 수 있습니다
- 대용량 데이터의 경우 CSV 다운로드가 더 빠를 수 있습니다

