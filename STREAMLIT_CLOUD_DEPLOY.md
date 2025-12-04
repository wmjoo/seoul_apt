# Streamlit Cloud 배포 가이드

## 배포 단계

### 1. Streamlit Cloud 접속 및 로그인
- https://share.streamlit.io/ 접속
- GitHub 계정으로 로그인

### 2. 새 앱 배포
1. "New app" 버튼 클릭
2. 다음 정보 입력:
   - **Repository**: `wmjoo/seoul_apt`
   - **Branch**: `main`
   - **Main file path**: `app.py`
   - **Python version**: `3.11` (또는 requirements.txt에 맞게)

### 3. Secrets 설정 (중요!)

앱 설정에서 "Secrets" 탭을 클릭하고 다음 형식으로 입력:

```toml
[secrets]
data_password = "6398"

# API 키는 환경변수로 설정하는 것을 권장합니다
# 또는 아래와 같이 secrets에 추가할 수 있습니다
# PUBLIC_DATA_API_KEY = "your_api_key_here"
# SEOUL_DATA_API_KEY = "your_seoul_api_key_here"
```

**또는 환경변수로 설정:**
- Streamlit Cloud의 "Settings" > "Environment variables"에서:
  - `PUBLIC_DATA_API_KEY`: 공공데이터포털 API 키
  - `SEOUL_DATA_API_KEY`: 서울 열린데이터광장 API 키

### 4. 배포 완료
- "Deploy" 버튼 클릭
- 배포가 완료되면 자동으로 URL이 생성됩니다
- 예: `https://seoul-apt.streamlit.app`

## 주의사항

1. **데이터 파일**: 
   - CSV 파일은 Git에 커밋되지 않으므로, Streamlit Cloud에서는 데이터가 없을 수 있습니다
   - "새 데이터 생성" 기능을 사용하여 API로 데이터를 수집할 수 있습니다

2. **API 키**:
   - API 키는 반드시 Secrets 또는 환경변수로 설정해야 합니다
   - 코드에 직접 입력하지 마세요

3. **첫 배포**:
   - 첫 배포 시 패키지 설치로 인해 시간이 걸릴 수 있습니다
   - 배포 로그를 확인하여 오류가 없는지 확인하세요

## 문제 해결

### 배포 실패 시
- 배포 로그 확인: Streamlit Cloud 대시보드에서 "Logs" 확인
- requirements.txt 확인: 모든 패키지가 올바른지 확인
- Secrets 확인: 필요한 환경변수/Secrets가 설정되었는지 확인

### 데이터가 보이지 않을 때
- "새 데이터 생성" 기능 사용 (비밀번호: 6398)
- 또는 로컬에서 생성한 CSV 파일을 GitHub에 커밋 (권장하지 않음)

