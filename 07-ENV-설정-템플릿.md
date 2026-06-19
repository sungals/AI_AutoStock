# .env 설정 템플릿

> 시스템 실행에 필요한 모든 환경변수 목록입니다. `.env.example` 파일로 저장하고,
> 실제 `.env`에 값을 채워서 사용하세요. `.env`는 절대 git에 커밋하지 마세요.

---

## .env.example (전체 템플릿)

```dotenv
# =============================================================
# TTAK Quant .env 설정 템플릿
# 이 파일을 .env로 복사한 후 실제 값을 입력하세요.
# cp .env.example .env
# chmod 600 .env
# =============================================================

# ─────────────────────────────────────────────────────────────
# [필수] Flask 기본 설정
# ─────────────────────────────────────────────────────────────

# Flask 세션 암호화 키 (32바이트 hex, 아래 명령으로 생성)
# python3 -c "import secrets; print(secrets.token_hex(32))"
SECRET_KEY=

# Flask 실행 환경 (production 권장)
# development: 디버그 모드 활성화, SECURE 쿠키 비활성화
# production:  최적화 모드, SECURE 쿠키 활성화 (HTTPS 필수)
FLASK_ENV=production

# ─────────────────────────────────────────────────────────────
# [필수] DART OpenAPI 키
# 발급: https://opendart.fss.or.kr
# 용도: 재무제표, DART 공시, 기업 고유번호 수집
# 한도: 10,000건/일
# ─────────────────────────────────────────────────────────────

OPENDART_API_KEY=

# ─────────────────────────────────────────────────────────────
# [필수] 네이버 검색 API
# 발급: https://developers.naver.com → [애플리케이션 등록] → 검색 API
# 용도: 종목 뉴스 수집 (한도 초과 시 크롤링으로 자동 폴백)
# 한도: 25,000건/일
# ─────────────────────────────────────────────────────────────

NAVER_CLIENT_ID=
NAVER_CLIENT_SECRET=

# ─────────────────────────────────────────────────────────────
# [권장] FRED API — 미국 연방준비은행 경제지표
# 발급: https://fred.stlouisfed.org/docs/api/api_key.html (무료)
# 용도: 연방기금금리(FFR), 실업률, CPI, 10Y-2Y 스프레드
# 없으면: 매크로 수집 시 FRED 데이터만 스킵됨
# ─────────────────────────────────────────────────────────────

FRED_API_KEY=

# ─────────────────────────────────────────────────────────────
# [권장] ECOS API — 한국은행 경제통계
# 발급: https://ecos.bok.or.kr/api/ → API 키 신청
# 용도: 한국 기준금리, CPI, M2 통화량
# 없으면: 한국 거시 지표 수집 스킵됨
# ─────────────────────────────────────────────────────────────

ECOS_API_KEY=

# ─────────────────────────────────────────────────────────────
# [선택] R-ONE API — 한국부동산원
# 발급: https://www.reb.or.kr/r-one/openapi (승인 필요, 1~3일)
# 용도: 아파트 매매가격지수
# 없으면: 부동산 지수 수집 스킵됨
# ─────────────────────────────────────────────────────────────

REB_API_KEY=

# ─────────────────────────────────────────────────────────────
# [선택] Anthropic Claude API — AI 일일 분석
# 발급: https://console.anthropic.com → API Keys
# 용도: 일일 파이프라인 완료 후 AI 시장 분석 리포트 생성
# 없으면: AI 분석 단계 자동 스킵 (나머지 파이프라인 정상 동작)
# ─────────────────────────────────────────────────────────────

ANTHROPIC_API_KEY=

# ─────────────────────────────────────────────────────────────
# [자동매매 시 필수] 한국투자증권 KIS OpenAPI
# 발급: https://securities.koreainvestment.com → Open Trading → OpenAPI 신청
# 용도: 실시간 시세 조회, 매수/매도 주문 실행
#
# ⚠️  KOREAINVESTMENT_MODE=mock 이 기본값입니다.
#     실제 주문을 실행하려면 prod로 변경하고,
#     반드시 충분한 모의투자 검증(최소 3개월) 후 진행하세요.
# ─────────────────────────────────────────────────────────────

KOREAINVESTMENT_APP_ID=
KOREAINVESTMENT_SECRET=

# 계좌번호 형식: XXXXXXXXXX-XX (하이픈 포함)
KOREAINVESTMENT_ACCOUNT=

# mock: 모의투자 (안전, 실제 주문 없음) — 기본값
# prod: 실제 계좌 (실제 자산 영향 — 충분한 검증 후 사용)
KOREAINVESTMENT_MODE=mock

# ─────────────────────────────────────────────────────────────
# [서버 배포 시] 경로 설정
# ─────────────────────────────────────────────────────────────

# Nginx 리버스 프록시 서브 경로
# 예: /ttakquant → http://domain.com/ttakquant 로 접근
# 루트 경로로 배포 시: 빈칸 또는 /
# Nginx rewrite로 prefix를 제거한 후 Flask로 전달하는 구조에서 사용
BASE_PATH=/ttakquant

# DB 파일 절대 경로 (기본값: {app_dir}/quant_data.db)
# ⚠️  특별한 이유가 없으면 설정하지 마세요.
#     잘못된 경로 설정 시 빈 DB를 가리켜 로그인 불가 버그 발생
# DB_PATH=/absolute/path/to/quant_data.db

# 출력 디렉토리 절대 경로 (기본값: {app_dir}/output)
# config.py가 자동으로 디렉토리를 생성하므로 보통 설정 불필요
# OUTPUT_DIR=/absolute/path/to/output

# ─────────────────────────────────────────────────────────────
# [선택] Ollama 로컬 LLM (별도 서버 설치 필요)
# 설치: https://ollama.ai (GPU 서버 권장)
# 용도: 차트 패턴 해석, 감성 분석 보강, 알고리즘 제안
# 없으면: AI 분석 레이어 자동 스킵 (graceful degradation)
# ─────────────────────────────────────────────────────────────

# Ollama 서버 URL (기본: http://localhost:11434)
# OLLAMA_BASE_URL=http://192.168.1.100:11434
```

---

## 변수별 상세 설명

### SECRET_KEY

Flask 세션, CSRF 토큰 암호화에 사용합니다. 절대로 공개하지 마세요.

```bash
# 생성 방법
python3 -c "import secrets; print(secrets.token_hex(32))"

# 출력 예시 (이 값은 사용하지 마세요 — 예시용)
# a3f8d2e1c4b7a6950f2e3d1c8a7b6e5f4a3d2c1b0e9f8a7b6c5d4e3f2a1b0c9
```

앱 시작 시 `SECRET_KEY`가 없으면 즉시 오류가 발생합니다:

```python
_secret_key = os.environ.get('SECRET_KEY')
if not _secret_key:
    raise RuntimeError("SECRET_KEY 환경변수가 설정되지 않았습니다.")
```

### OPENDART_API_KEY

DART 재무제표 수집의 핵심 키입니다. 이 키가 없으면 재무 지표 계산이 불가능합니다.

```python
# 사용 예 (financial_fetcher.py)
url = "https://opendart.fss.or.kr/api/xbrl_taxon_pdls.json"
params = {
    "crtfc_key": os.environ.get('OPENDART_API_KEY', ''),
    ...
}
```

일일 10,000건 한도를 추적하고 초과 시 자동으로 수집을 멈춥니다.

### KOREAINVESTMENT_MODE

| 값 | 동작 |
|----|------|
| `mock` | 모의투자 API 서버 사용, 실제 주문 없음 (기본값, 안전) |
| `prod` | 실제 계좌 API 서버 사용, 실제 주문 실행 |

`mock` 모드에서는 실제 돈이 움직이지 않습니다.
`prod`로 전환하기 전에 최소 3개월 이상의 모의투자 결과를 검토하세요.

### BASE_PATH

Nginx 서브 경로 배포 시 사용합니다. 이 값이 Jinja2 템플릿에 전달되어
JavaScript에서 API URL을 올바르게 구성합니다.

```jinja2
{# base.html #}
<script>
    const BASE_PATH = "{{ config['BASE_PATH'] }}";
    // 이후 JS에서: fetch(BASE_PATH + '/api/screening/results')
</script>
```

---

## 환경별 .env 파일 관리

### 개발 환경

```dotenv
SECRET_KEY=dev-secret-key-not-for-production
FLASK_ENV=development
OPENDART_API_KEY=실제_개발_키
KOREAINVESTMENT_MODE=mock
BASE_PATH=
# DB_PATH, OUTPUT_DIR 생략 → 기본값 사용
```

### 프로덕션 환경 (서버)

```dotenv
SECRET_KEY=실제_32바이트_hex_키
FLASK_ENV=production
OPENDART_API_KEY=실제_운영_키
NAVER_CLIENT_ID=실제_운영_키
NAVER_CLIENT_SECRET=실제_운영_키
FRED_API_KEY=실제_운영_키
ECOS_API_KEY=실제_운영_키
KOREAINVESTMENT_APP_ID=실제_운영_키
KOREAINVESTMENT_SECRET=실제_운영_키
KOREAINVESTMENT_ACCOUNT=실제_계좌번호
KOREAINVESTMENT_MODE=mock   # 검증 완료 전까지 mock 유지
BASE_PATH=/ttakquant
# DB_PATH, OUTPUT_DIR 생략 → 기본값 사용
```

---

## 보안 주의사항

1. `.env` 파일을 절대 git에 포함하지 마세요.

```gitignore
# .gitignore에 반드시 포함
.env
*.db
*.db-wal
*.db-shm
output/
logs/
```

2. `.env` 파일 권한을 제한하세요.

```bash
chmod 600 .env         # 소유자만 읽기/쓰기
ls -la .env            # -rw------- 확인
```

3. 서버 이전 시 `.env` 파일을 직접 복사하거나 직접 입력하세요.
   이메일이나 채팅으로 API 키를 전송하지 마세요.

4. API 키가 노출된 경우 즉시 해당 서비스에서 키를 재발급하세요.

---

## 환경변수 로드 확인

앱 시작 후 환경변수가 올바르게 로드되었는지 확인합니다.

```python
# 임시 확인 스크립트 (실행 후 삭제)
import os
from dotenv import load_dotenv
load_dotenv('.env')

required = ['SECRET_KEY', 'OPENDART_API_KEY']
optional = ['NAVER_CLIENT_ID', 'FRED_API_KEY', 'ECOS_API_KEY', 'REB_API_KEY',
            'KOREAINVESTMENT_APP_ID', 'ANTHROPIC_API_KEY']

print("=== 필수 변수 ===")
for key in required:
    val = os.environ.get(key, '')
    status = "OK" if val else "MISSING"
    print(f"  {key}: {status} ({len(val)} chars)")

print("\n=== 선택 변수 ===")
for key in optional:
    val = os.environ.get(key, '')
    status = "설정됨" if val else "미설정 (해당 기능 스킵)"
    print(f"  {key}: {status}")
```

---

이전 문서: [06-배포-운영-가이드.md](./06-배포-운영-가이드.md)

---

## 문서 목록

| 문서 | 내용 |
|------|------|
| [00-프로젝트-개요.md](./00-프로젝트-개요.md) | 전체 시스템 소개 |
| [01-기술-스택.md](./01-기술-스택.md) | 사용 라이브러리 목록 |
| [02-외부-API-가이드.md](./02-외부-API-가이드.md) | 외부 API 발급 방법 |
| [03-시스템-아키텍처.md](./03-시스템-아키텍처.md) | 모듈 구조 + 데이터 흐름 |
| [04-DB-스키마.md](./04-DB-스키마.md) | SQLite 전체 테이블 스키마 |
| [05-구현-가이드.md](./05-구현-가이드.md) | Phase별 구현 방법 |
| [06-배포-운영-가이드.md](./06-배포-운영-가이드.md) | 서버 설치 및 운영 |
| [07-ENV-설정-템플릿.md](./07-ENV-설정-템플릿.md) | 이 문서 |
