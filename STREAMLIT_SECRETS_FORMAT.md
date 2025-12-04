# Streamlit Cloud Secrets 설정 가이드

## 올바른 형식

Streamlit Cloud의 Secrets는 **TOML 형식**을 사용합니다. 아래 형식으로 입력하세요:

```toml
[secrets]
data_password = "6398"
PUBLIC_DATA_API_KEY = "실제_API_키_값"
SEOUL_DATA_API_KEY = "실제_API_키_값"
```

**주의사항:**
- 주석(`#`)은 사용할 수 없습니다
- `[secrets]` 섹션 헤더가 필요합니다
- 따옴표로 감싸야 합니다
- `~~~` 같은 마스킹 문자는 제거하고 실제 키 값만 입력하세요
- 모든 값은 `[secrets]` 섹션 안에 있어야 합니다

## 현재 코드 동작 방식

코드는 다음 우선순위로 설정값을 읽습니다:
1. **Streamlit Secrets** (최우선)
2. **환경변수** (`os.getenv()`)
3. **.env 파일**
4. **기본값**

따라서 Streamlit Cloud에서는 Secrets에 모든 값을 설정하면 됩니다.

## 올바른 Secrets 설정 예시

Streamlit Cloud의 **Secrets**에 다음을 입력:

```toml
[secrets]
data_password = "6398"
PUBLIC_DATA_API_KEY = "실제_API_키_값_여기"
SEOUL_DATA_API_KEY = "실제_API_키_값_여기"
```

**중요:**
- `[secrets]` 섹션 헤더 필수
- 모든 값은 따옴표로 감싸기
- 주석(`#`) 사용 불가
- 실제 키 값만 입력 (마스킹 문자 제거)

## 잘못된 형식 (사용하지 마세요)

```toml
# 이렇게 하지 마세요 - 주석 포함
data_password = "6398"
PUBLIC_DATA_API_KEY="~~~%2FWl9%2FoUw%3D%3D"  # 주석과 마스킹 문자 포함
SEOUL_DATA_API_KEY="~~~4978"  # 마스킹 문자 포함
```

또는 섹션 헤더 없이:
```toml
# 이렇게 하지 마세요 - [secrets] 섹션 헤더 없음
data_password = "6398"
PUBLIC_DATA_API_KEY = "키값"
```

## 올바른 형식 (최종)

```toml
[secrets]
data_password = "6398"
PUBLIC_DATA_API_KEY = "실제_키_값"
SEOUL_DATA_API_KEY = "실제_키_값"
```

