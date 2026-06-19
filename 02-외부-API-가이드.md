# 외부 API 가이드

> 이 시스템이 사용하는 모든 외부 API 목록입니다. 각 API의 발급 방법, 제공 데이터, 한도, Rate Limit을
> 상세히 설명합니다. 우선순위는 필수 → 권장 → 선택 순입니다.

---

## 우선순위 요약

| API | 우선순위 | 키 필요 | 용도 |
|-----|----------|---------|------|
| DART OpenAPI | 필수 | O | 재무제표, 공시, 기업정보 |
| 네이버 검색 API | 필수 | O | 뉴스 검색 |
| FRED API | 권장 | O | 미국 경제지표 |
| ECOS API | 권장 | O | 한국 경제지표 |
| R-ONE API | 선택 | O | 부동산 매매가격지수 |
| KIS OpenAPI | 자동매매 시 필수 | O | 실시간 시세, 주문 |
| Anthropic Claude | 선택 | O | AI 일일 분석 리포트 |
| pykrx | 필수 | X | KRX 주식 데이터 |
| yfinance | 필수 | X | 글로벌 시장 데이터 |
| FinanceDataReader | 필수 | X | KOSPI/KOSDAQ 지수 |

---

## 1. DART OpenAPI (필수)

**제공 기관**: 금융감독원 전자공시시스템

### 발급 방법

1. https://opendart.fss.or.kr 접속
2. 회원가입 (이메일 인증)
3. 상단 메뉴 → [인증키 신청/관리] → [인증키 신청]
4. 사용 목적 입력 후 신청 (즉시 발급)
5. 발급된 인증키를 `.env`의 `OPENDART_API_KEY`에 설정

### 제공 데이터

| 엔드포인트 | 데이터 | API 경로 |
|-----------|--------|---------|
| 기업 고유번호 | DART corp_code ↔ 종목코드 매핑 | `/api/corpCode.xml` |
| 재무제표 (xbrl) | IFRS 재무제표 전 계정 | `/api/xbrl_taxon_pdls.json` |
| 단일회사 전기간 재무 | 주요 재무 계정 연도별 | `/api/fnlttMultiAcntAll.json` |
| 공시 목록 | 사업보고서, IR, 특수공시 등 | `/api/list.json` |
| 배당 정보 | 주당 배당금, 배당수익률 | `/api/alotMatter.json` |
| 대량보유 보고서 | 5% 이상 주주 현황 | `/api/majorstock.json` |

### 한도 및 Rate Limit

| 항목 | 기준 |
|------|------|
| 일일 호출 한도 | 10,000건 |
| 권장 호출 간격 | 0.5초 이상 |
| 한도 초과 시 | HTTP 429 또는 오류 응답 코드 반환 |

### 구현 시 주의사항

**CFS-first 폴백 패턴**: DART 재무제표는 연결재무제표(CFS) 우선으로 조회하고,
없으면 개별재무제표(OFS)로 폴백합니다.

```python
# 올바른 구현 패턴
for fs_div in ('CFS', 'OFS'):
    url = "https://opendart.fss.or.kr/api/xbrl_taxon_pdls.json"
    params = {
        "crtfc_key": API_KEY,
        "corp_code": corp_code,
        "bsns_year": bsns_year,
        "reprt_code": "11011",  # 사업보고서
        "fs_div": fs_div,
    }
    result = requests.get(url, params=params).json()
    if result.get('status') == '000':
        return result['list']
```

**DART 보고서 코드:**

| 코드 | 보고서 종류 |
|------|------------|
| `11011` | 사업보고서 (연간, 4Q) |
| `11012` | 반기보고서 (2Q) |
| `11013` | 1분기보고서 |
| `11014` | 3분기보고서 |

**IFRS 계정 과목 ID (주요 항목):**

| 계정 | account_id |
|------|------------|
| 자산총계 | `ifrs-full_Assets` |
| 부채총계 | `ifrs-full_Liabilities` |
| 자본총계 | `ifrs-full_Equity` |
| 매출액 | `ifrs-full_Revenue` |
| 영업이익 | `dart_OperatingIncomeLoss` |
| 당기순이익 | `ifrs-full_ProfitLoss` |
| 영업활동현금흐름 | `ifrs-full_CashFlowsFromUsedInOperatingActivities` |
| 재고자산 | `ifrs-full_Inventories` |

**no-data 캐시 패턴**: 데이터가 없는 기업을 반복 조회하지 않도록 `financial_no_data`
테이블에 캐시하고, 조회 전 먼저 확인합니다.

```python
# no-data 캐시 확인 (→ 04-DB-스키마.md의 financial_no_data 테이블 참조)
row = conn.execute(
    "SELECT last_tried FROM financial_no_data WHERE corp_code=? AND bsns_year=? AND reprt_code=?",
    (corp_code, bsns_year, reprt_code)
).fetchone()
if row:
    return None  # 캐시 히트 → 스킵
```

---

## 2. 네이버 검색 API (필수)

**제공 기관**: 네이버 개발자 센터

### 발급 방법

1. https://developers.naver.com 접속
2. 네이버 계정으로 로그인
3. [Application] → [애플리케이션 등록]
4. 애플리케이션 이름 입력
5. 사용 API: **검색** 선택
6. 등록 후 **Client ID**와 **Client Secret** 확인
7. `.env`에 `NAVER_CLIENT_ID`, `NAVER_CLIENT_SECRET` 설정

### 제공 데이터

| API | 엔드포인트 | 데이터 |
|-----|-----------|--------|
| 뉴스 검색 | `/v1/search/news.json` | 뉴스 기사 제목/요약/URL/날짜 |
| 데이터랩 | `/v1/datalab/search` | 검색어 트렌드 지수 |

### 뉴스 검색 구현

```python
import requests

NAVER_SEARCH_URL = "https://openapi.naver.com/v1/search/news.json"

headers = {
    "X-Naver-Client-Id": os.environ['NAVER_CLIENT_ID'],
    "X-Naver-Client-Secret": os.environ['NAVER_CLIENT_SECRET'],
}

params = {
    "query": f"{corp_name} 주식",
    "display": 100,          # 최대 100건
    "start": 1,
    "sort": "date",          # 최신순
}

response = requests.get(NAVER_SEARCH_URL, headers=headers, params=params)
articles = response.json()['items']
```

### 한도 및 폴백

| 항목 | 기준 |
|------|------|
| 일일 호출 한도 | 25,000건 |
| 초과 시 처리 | 크롤링 방식으로 자동 폴백 |
| 일일 사용량 추적 | `api_usage` 테이블 (`provider='naver'`) |

한도 초과 감지 및 폴백 구현:

```python
def _check_naver_api_quota(conn) -> bool:
    """True: API 사용 가능, False: 한도 초과(크롤링 폴백 필요)."""
    today = date.today().isoformat()
    row = conn.execute(
        "SELECT calls_made FROM api_usage WHERE usage_date=? AND provider='naver'",
        (today,)
    ).fetchone()
    if row and row['calls_made'] >= 25000:
        return False  # 한도 초과
    return True
```

---

## 3. FRED API (권장)

**제공 기관**: 미국 세인트루이스 연방준비은행

### 발급 방법

1. https://fred.stlouisfed.org/docs/api/api_key.html 접속
2. 무료 계정 생성
3. [My Account] → [API Keys] → [Request API Key]
4. 용도 설명 입력 후 요청 (즉시 발급)
5. `.env`의 `FRED_API_KEY`에 설정

### 제공 데이터 (주요 시리즈)

| 시리즈 ID | 데이터 | 설명 |
|-----------|--------|------|
| `DFF` | 연방기금금리 (FFR) | 미국 기준금리 (일간) |
| `UNRATE` | 실업률 | 월간 |
| `CPIAUCSL` | 소비자물가지수 | CPI 월간 |
| `T10Y2Y` | 10Y-2Y 스프레드 | 장단기 금리 역전 지표 |
| `FEDFUNDS` | 실효 연방기금금리 | 월간 평균 |
| `GS10` | 10년 국채 금리 | 일간 |

### 구현

```python
from fredapi import Fred

fred = Fred(api_key=os.environ.get('FRED_API_KEY'))

# 시리즈 조회
ffr_series = fred.get_series('DFF', observation_start='2020-01-01')
# → pandas.Series (날짜 인덱스, float 값)
```

### 한도

| 항목 | 기준 |
|------|------|
| 일일 호출 한도 | 실질적으로 무제한 (합리적 사용 기준) |
| API 키 없을 때 | `fredapi` 자체 오류 처리 필요 |

---

## 4. ECOS API (권장)

**제공 기관**: 한국은행 경제통계시스템

### 발급 방법

1. https://ecos.bok.or.kr/api/ 접속
2. 회원가입 (한국은행 사이트 통합 계정)
3. [API 키 신청] 메뉴에서 신청
4. 이메일로 발급된 키를 `.env`의 `ECOS_API_KEY`에 설정

### 제공 데이터 (주요 통계코드)

| 통계코드 | 데이터 | 빈도 |
|---------|--------|------|
| `722Y001` | 한국은행 기준금리 | 통화정책 결정 시 |
| `901Y009` | 소비자물가지수 (CPI) | 월간 |
| `101Y002` | M2 통화량 | 월간 |

### 구현

```python
import requests

ECOS_URL = "https://ecos.bok.or.kr/api/StatisticSearch"

params = {
    "apiKey": os.environ.get('ECOS_API_KEY'),
    "returnType": "json",
    "statCode": "722Y001",      # 기준금리
    "cycle": "M",               # 월간
    "startDate": "202001",
    "endDate": "202601",
    "itemCode1": "0101000",
}

url = f"{ECOS_URL}/{params['apiKey']}/json/kr/1/100/{params['statCode']}/{params['cycle']}/{params['startDate']}/{params['endDate']}/{params['itemCode1']}"
response = requests.get(url)
data = response.json()
```

### 한도

| 항목 | 기준 |
|------|------|
| 일일 호출 한도 | 10,000건 |
| API 키 없을 때 | 해당 수집 단계 graceful skip |

---

## 5. R-ONE API (선택)

**제공 기관**: 한국부동산원

### 발급 방법

1. https://www.reb.or.kr/r-one/openapi 접속 (Open API 메뉴)
2. 회원가입 후 서비스 신청
3. 활용 목적 입력 → 승인 후 API 키 발급 (1~3일 소요)
4. `.env`의 `REB_API_KEY`에 설정

### 제공 데이터

| 데이터 | 설명 |
|--------|------|
| 아파트 매매가격지수 | 전국/지역별 아파트 매매 가격 지수 (주간) |

### 구현

```python
import requests

url = "http://openapi.reb.or.kr/OpenAPI_ToolInstallPackage/service/rest/AptTradeSvc/getRealEstateTrend"
params = {
    "ServiceKey": os.environ.get('REB_API_KEY'),
    "pageNo": 1,
    "numOfRows": 50,
    "type": "json",
    "startMonth": "202001",
    "endMonth": "202601",
    "regionCode": "0000",    # 전국
}
response = requests.get(url, params=params)
```

### API 키 없을 때 처리

부동산 데이터는 선택 항목이므로, API 키가 없거나 수집에 실패해도 나머지 파이프라인은 계속 진행합니다.

```python
try:
    reb_data = fetch_reb_data()
except Exception as e:
    logger.warning(f"R-ONE API 수집 실패 (계속): {e}")
    reb_data = None
```

---

## 6. 한국투자증권 KIS OpenAPI (자동매매 시)

**제공 기관**: 한국투자증권 (Korea Investment & Securities)

### 발급 방법

1. 한국투자증권 계좌 개설 (비대면 가능)
2. https://securities.koreainvestment.com 접속
3. [트레이딩] → [Open Trading] → [오픈 API]
4. API 서비스 신청 (심사 후 승인, 1~3일)
5. 모의투자(Mock) 신청 별도 가능
6. 발급된 키를 `.env`에 설정

### 환경변수

```
KOREAINVESTMENT_APP_ID=     # 앱 키 (App Key)
KOREAINVESTMENT_SECRET=     # 앱 시크릿 (App Secret)
KOREAINVESTMENT_ACCOUNT=    # 계좌번호 (XXXXXXXXXX-XX 형식)
KOREAINVESTMENT_MODE=mock   # mock(모의투자) 또는 prod(실제)
```

### Mock 모드 vs Live 모드

| 항목 | Mock | Live |
|------|------|------|
| API 기반 URL | `https://openapivts.koreainvestment.com:29443` | `https://openapi.koreainvestment.com:9443` |
| 실제 주문 | 없음 | 있음 |
| 잔고 | 가상 잔고 | 실제 잔고 |
| 안전성 | 완전 안전 | 실제 자산 영향 |

**안전 가드**: `KOREAINVESTMENT_MODE=mock`이 기본값입니다.
Live 모드 전환은 반드시 충분한 모의투자 검증 후 진행하세요.

### 제공 기능

| 기능 | API 경로 |
|------|---------|
| 액세스 토큰 발급 | `POST /oauth2/tokenP` |
| 잔고 조회 | `GET /uapi/domestic-stock/v1/trading/inquire-balance` |
| 현재가 조회 | `GET /uapi/domestic-stock/v1/quotations/inquire-price` |
| 매수 주문 | `POST /uapi/domestic-stock/v1/trading/order-cash` |
| 매도 주문 | `POST /uapi/domestic-stock/v1/trading/order-cash` |
| WebSocket 실시간 시세 | `wss://openapi.koreainvestment.com:21000` |

### 실시간 WebSocket 구독

```python
import websockets
import asyncio

async def subscribe_realtime(stock_code: str):
    uri = "wss://openapi.koreainvestment.com:21000"
    async with websockets.connect(uri) as ws:
        # 실시간 시세 구독 요청 (H0STCNT0)
        subscribe_msg = {
            "header": {
                "approval_key": approval_key,
                "custtype": "P",
                "tr_type": "1",      # 등록
                "content-type": "utf-8",
            },
            "body": {
                "input": {
                    "tr_id": "H0STCNT0",
                    "tr_key": stock_code,
                }
            }
        }
        await ws.send(json.dumps(subscribe_msg))
        # 이후 수신 루프...
```

---

## 7. Anthropic Claude API (선택)

**제공 기관**: Anthropic

### 발급 방법

1. https://console.anthropic.com 접속
2. 계정 생성 후 카드 등록
3. [API Keys] → [Create Key]
4. `.env`의 `ANTHROPIC_API_KEY`에 설정

### 용도

매일 파이프라인 완료 후 `claude_analyzer.py`가 호출되어 아래 항목의 AI 분석 리포트를 생성합니다.

- 시장 국면 평가 (현재 bull/bear/sideways 판단 근거)
- 상위 전략 조합 추천
- 실패 패턴 식별
- 알고리즘 개선 제안

### API 키 없을 때 처리

```python
api_key = os.environ.get('ANTHROPIC_API_KEY')
if not api_key:
    logger.info("ANTHROPIC_API_KEY 없음 — AI 분석 단계 스킵")
    return None
```

---

## 8. pykrx (API 키 불필요)

KRX(한국거래소) 데이터를 직접 수집하는 라이브러리입니다. 별도 인증 없이 사용 가능합니다.

```bash
pip install pykrx
```

### 주요 데이터 수집 방법

```python
from pykrx import stock

# KOSPI 종목 리스트
tickers = stock.get_market_ticker_list(market='KOSPI')

# 종목 OHLCV
df = stock.get_market_ohlcv_by_date('20260101', '20260305', '005930')

# 시가총액
df = stock.get_market_cap_by_date('20260305', '20260305', '005930')

# 투자자별 매매 (종목)
df = stock.get_market_trading_value_by_date('20260101', '20260305', '005930',
                                             detail=True)

# 공매도 현황
df = stock.get_shorting_volume_by_date('20260101', '20260305', '005930')

# 시장 전체 투자자 매매 (자금흐름)
df = stock.get_market_trading_value_by_investor('20260305', '20260305', 'KOSPI')
```

### Rate Limit 주의

```python
import time

for ticker in tickers:
    data = stock.get_market_ohlcv_by_date(start, end, ticker)
    time.sleep(1.0)   # 1초 딜레이 필수 — 빠르게 호출하면 차단될 수 있음
```

---

## 9. yfinance (API 키 불필요)

Yahoo Finance 데이터를 수집합니다. 별도 인증 없이 사용 가능합니다.

```bash
pip install yfinance
```

### 주요 심볼 목록

```python
import yfinance as yf

symbols = {
    'CL=F':    'WTI 원유',
    'GC=F':    '금',
    'USDKRW=X': '달러/원 환율',
    'BTC-USD': '비트코인',
    'ETH-USD': '이더리움',
    '^VIX':    'VIX 공포지수',
    '^GSPC':   'S&P 500',
    '^KS11':   'KOSPI',
    '^KQ11':   'KOSDAQ',
}

# 일간 데이터 수집
df = yf.download('CL=F', start='2020-01-01', progress=False)
# → OHLCV DataFrame
```

### Rate Limit

Yahoo Finance는 공식적인 Rate Limit을 명시하지 않지만, 과도한 호출 시 일시 차단될 수 있습니다.
종목별 수집 시 0.5~1초 딜레이를 권장합니다.

---

## 10. FinanceDataReader (API 키 불필요)

KOSPI/KOSDAQ 지수 보조 수집에 사용합니다.

```bash
pip install finance-datareader
```

```python
import FinanceDataReader as fdr

kospi = fdr.DataReader('KS11', '2020-01-01')  # KOSPI 종가 시계열
kosdaq = fdr.DataReader('KQ11', '2020-01-01')  # KOSDAQ 종가 시계열
```

---

## 11. API 사용량 추적 및 모니터링

시스템 내에서 모든 API 호출을 `api_usage` 테이블에 기록합니다.

```sql
CREATE TABLE api_usage (
    usage_date   TEXT NOT NULL,
    provider     TEXT NOT NULL,     -- 'opendart', 'naver', 'fred', 'ecos', 'reb' 등
    calls_made   INTEGER NOT NULL DEFAULT 0,
    error_count  INTEGER NOT NULL DEFAULT 0,
    updated_at   TEXT DEFAULT (datetime('now')),
    PRIMARY KEY (usage_date, provider)
);
```

대시보드에서 오늘 사용량 / 잔여 한도를 실시간으로 확인할 수 있습니다.

```python
def log_api_usage(conn, provider: str, success: bool = True):
    """API 호출 후 사용량 기록."""
    today = date.today().isoformat()
    conn.execute("""
        INSERT INTO api_usage (usage_date, provider, calls_made, error_count)
        VALUES (?, ?, 1, ?)
        ON CONFLICT(usage_date, provider) DO UPDATE SET
            calls_made  = calls_made  + 1,
            error_count = error_count + ?,
            updated_at  = datetime('now')
    """, (today, provider, 0 if success else 1, 0 if success else 1))
```

---

## 12. Decorator 기반 Rate Limiting

API 호출 함수에 `@rate_limited` 데코레이터를 적용하여 Rate Limit을 일관되게 관리합니다.

```python
import time
import functools

def rate_limited(min_interval: float = 1.0):
    """함수 호출 간 최소 대기 시간을 보장하는 데코레이터."""
    last_called = [0.0]

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            elapsed = time.time() - last_called[0]
            if elapsed < min_interval:
                time.sleep(min_interval - elapsed)
            result = func(*args, **kwargs)
            last_called[0] = time.time()
            return result
        return wrapper
    return decorator

# 사용 예
@rate_limited(min_interval=0.5)  # DART: 0.5초 간격
def fetch_financial_statement(corp_code: str, bsns_year: str) -> dict:
    ...

@rate_limited(min_interval=1.0)  # pykrx: 1.0초 간격
def fetch_ohlcv(stock_code: str, start: str, end: str):
    ...
```

---

다음 문서: [03-시스템-아키텍처.md](./03-시스템-아키텍처.md)
