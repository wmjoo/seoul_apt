# 서울 아파트 검색

Streamlit 앱입니다. `[tracker_users]` 계정으로 로그인한 뒤에만 화면이 열립니다. 아파트 목록·지도·통계는 저장소의 메타데이터 CSV를 쓰고, 실거래는 국토부 API로 받아 비공개 Google 시트에 구별로 저장합니다.

배포 예: https://seoul-apt.streamlit.app

## 화면

로그인 후 상단 메뉴와 사이드바가 보입니다. 메뉴는 고른 화면만 그리므로, 처음에는 조회에 필요한 구 시트만 읽습니다. 로그아웃은 사이드바입니다.

| 화면 | 하는 일 |
|---|---|
| 실거래가 조회 | 구·동·단지 검색. 기간 슬라이더, 전용면적(동일 면적 묶기 기본), 1층 제외. 단지 선택 시 시세·거래량 차트와 KB 반기 하락기 음영 |
| 단지 비교 | 여러 단지를 같은 기간·면적으로 겹쳐 비교 |
| 실거래가 크롤링 | 추적 구 추가/삭제, 기간 수집. 6개월 이하는 다시 받고, 더 긴 기간은 완료된 구·월을 건너뜀 |
| 목록 / 지도 / 통계 | 사이드바 필터로 아파트 메타데이터를 보고 내려받음 |
| 설정 | `districts`에 있는 구마다 자동업데이트 온오프 |

로그인 직후, 설정에서 **켠 구**이면서 `LAST_REG_DT`가 오늘(서울)이 아니면 당월만 자동 수집합니다. 진행은 페이지 너비 프로그레스 바로 표시합니다.

날짜·수집 시각은 Cloud가 UTC여도 `Asia/Seoul`로 맞춥니다.

## 저장소

### 아파트 목록

앱은 아래 순서로 목록을 읽습니다.

1. 세션에 방금 만든 데이터
2. `seoul_apartments_metadata.csv` (저장소에 포함)
3. `seoul_apartments.csv`
4. 없으면 샘플 생성

사이드바「새 데이터 생성」은 `data_password`가 맞을 때만 보입니다. 목록/지도에는 `seoul_disrict_main_apt.csv`와 단지명을 맞춰 평수·실거래가 참고 컬럼을 붙입니다.

### 실거래 (Google 시트)

`[sheets]` + `[gcp_service_account]`가 있으면 시트를 씁니다. 없으면 로컬 `apt_trades.csv` / `tracked_districts.csv`로 떨어집니다. 이력 CSV는 Git에 올리지 마세요.

시트는 **링크가 있는 모든 사용자**가 아니라, 본인 구글 계정과 서비스 계정 이메일에만 공유하세요.

| 시트 | 내용 |
|---|---|
| `성북구` 등 구 이름 | 그 구 거래. 행 끝 `REG_DT` |
| `districts` | 구 메타. 코드가 읽고 쓰는 유일한 수집 메타 시트 |
| `trades` | 예전 통합 시트. 있으면 읽기만 함 |
| `collection_log` | 더 이상 쓰지 않음. `districts` 완료 연월이 비어 있을 때만 한 번 이관 |

`districts` 컬럼:

- `구`
- `자동업데이트` — `ON` / `OFF` (기본 `OFF`)
- `LAST_REG_DT` — 마지막 수집 시각
- `최초 거래일` / `최종 거래일`
- `완료시작연월` / `완료종료연월` — 달이 닫힌 뒤 수집된 연속 구간. 긴 기간 수집 시 이 구간은 건너뜀

거래 저장에 실패하면 완료 구간과 `LAST_REG_DT`를 남기지 않습니다. 같은 구·월을 다시 받을 때 조건이 같은 별개 거래는 지우지 않습니다.

시장 국면(회색 음영, 상승/하락 연평균)은 `data/seoul_market_monthly.json`(KB 서울 아파트 매매가격지수)을 씁니다. 앱 실행 중 지수를 다시 받지 않습니다. 재수집은 `python scripts/fetch_market_index.py`, 설명은 `data/README.md`.

## 로컬 실행

```bash
pip install -r requirements.txt
cp secrets.toml.example .streamlit/secrets.toml
streamlit run app.py
```

브라우저에서 http://localhost:8501

테스트:

```bash
python -m pytest tests
```

## Secrets

로컬은 `.streamlit/secrets.toml`, Cloud는 앱 Secrets에 같은 TOML을 넣습니다. 예시는 `secrets.toml.example`입니다. 비밀번호와 키는 Git에 커밋하지 마세요.

```toml
[secrets]
data_password = "데이터생성_비밀번호"
PUBLIC_DATA_API_KEY = "공공데이터포털_일반인증키"

[tracker_users]
family1 = "비밀번호1"

[sheets]
spreadsheet_id = "구글시트_ID"

[gcp_service_account]
type = "service_account"
# ... 서비스 계정 JSON 필드
```

- `[tracker_users]` 또는 `[secrets.tracker_users]`: 로그인 아이디 = 비밀번호. 없으면 앱에 들어갈 수 없습니다.
- `PUBLIC_DATA_API_KEY`: 국토부 아파트 매매 실거래 API. 수집·자동업데이트에 필요합니다.
- `data_password`: 사이드바 아파트 목록 재수집.
- `[sheets]` + `[gcp_service_account]`: 실거래 시트. 없으면 조회/수집이 비거나 로컬 CSV만 씁니다.
- Cloud에서 `private_key`는 삼중 따옴표 PEM 또는 `\n`이 들어간 한 줄로 넣으세요.

`SEOUL_DATA_API_KEY`는 아파트 메타데이터 크롤링(`crawl_metadata.py` / `crawler.py`)에만 씁니다. 실거래 수집에는 필요 없습니다.

자세한 Cloud 배포는 [STREAMLIT_CLOUD_DEPLOY.md](STREAMLIT_CLOUD_DEPLOY.md), Secrets 형식은 [STREAMLIT_SECRETS_FORMAT.md](STREAMLIT_SECRETS_FORMAT.md).

## 아파트 메타데이터 다시 받기

목록 CSV를 로컬에서 다시 만들 때:

```bash
# 서울 열린데이터광장 공동주택 API (SEOUL_DATA_API_KEY)
python crawl_metadata.py
```

또는 앱 사이드바「새 데이터 생성」. 인증키는 https://data.seoul.go.kr , 데이터셋은 [OA-15818](https://data.seoul.go.kr/dataList/OA-15818/A/1/datasetView.do). API 한도는 [API_GUIDE.md](API_GUIDE.md).

## 파일

```
seoul_apt/
├── app.py                      # Streamlit 엔트리. 로그인 게이트, 탭, 자동 수집
├── auth.py                     # tracker_users 로그인
├── molit_trades.py             # 국토부 실거래 수집·완료 구간
├── sheets_store.py             # Google 시트 (구별 거래 + districts)
├── seoul_time.py               # Asia/Seoul 시각
├── trade_controls.py           # 기간 슬라이더·전용면적
├── trade_compare.py            # 단지 비교
├── trade_metadata.py           # 단지 정보 표
├── market_cycles.py            # KB 지수 반기/연간 국면
├── crawler.py / crawl_metadata.py / config.py / utils.py
├── secrets.toml.example
├── seoul_apartments_metadata.csv
├── seoul_disrict_main_apt.csv
├── data/seoul_market_monthly.json
├── scripts/fetch_market_index.py
└── tests/
```

## 라이선스

교육 및 개인 사용 목적으로 제작되었습니다.
