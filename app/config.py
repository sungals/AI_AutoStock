"""전역 설정 — 경로, API 파라미터, 백테스트 신뢰성 레이어 설정.

Python 3.9 호환. (타입힌트는 Optional[...] 사용, X | None 금지)
"""
import os
from datetime import datetime

# ── .env 로딩 (있으면) — OPENDART_API_KEY 등 비밀값 ──
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env'))
except Exception:
    pass

# ── 분석 연도 ──
BUSINESS_YEAR = str(datetime.now().year - 1)        # 작년
PRIOR_BUSINESS_YEAR = str(datetime.now().year - 2)  # 재작년

# ── 경로 ──
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get('DB_PATH', os.path.join(BASE_DIR, 'quant_data.db'))
OUTPUT_DIR = os.environ.get('OUTPUT_DIR', os.path.join(BASE_DIR, 'output'))
BASE_PATH = os.environ.get('BASE_PATH', '').strip()

# ── 수집 Rate Limit ──
PYKRX_DELAY = 1.0
DART_DELAY = 0.5
NAVER_DELAY = 0.2

# ── DART OpenAPI ──
OPENDART_API_KEY = os.environ.get('OPENDART_API_KEY', '')
DART_BASE = 'https://opendart.fss.or.kr/api'
DART_CORPCODE_URL = DART_BASE + '/corpCode.xml'

# ── Naver Search API ──
NAVER_CLIENT_ID = os.environ.get('NAVER_CLIENT_ID', '')
NAVER_CLIENT_SECRET = os.environ.get('NAVER_CLIENT_SECRET', '')
NAVER_NEWS_URL = 'https://openapi.naver.com/v1/search/news.json'

# 정기보고서 코드 → 보고서명 키워드 (공시일 매칭용)
DART_REPRT_KEYWORD = {
    '11011': u'사업보고서',
    '11012': u'반기보고서',
    '11013': u'분기보고서',
    '11014': u'분기보고서',
}

# ============================================================
# 백테스트 신뢰성 레이어 설정 (docs/backtest-reliability/00-스펙-설계.md §6)
# ============================================================

COMMISSION_RATE = 0.00015        # 편도 수수료 (0.015%)
SLIPPAGE_BPS = 10.0              # 슬리피지 (10bp = 0.10%)

PIT_ANNUAL_LAG_DAYS = 90         # 사업보고서 공시 추정 지연 (회계연도 말 + N일)
PIT_QUARTER_LAG_DAYS = 45        # 분기/반기보고서 공시 추정 지연

PRICE_LIMIT_PCT = 0.30           # 상·하한가 ±30%
MIN_TRADE_VALUE_KRW = 100_000_000  # 최소 거래대금(유동성 필터)

OOS_FRACTION = 0.30              # Out-of-Sample 비중
MIN_DEFLATED_SR = 0.95           # 옵티마이저 반영 Deflated Sharpe 임계

# 증권거래세율 (매도 시 적용; 시행일 내림차순) — 'YYYY-MM-DD' 이상이면 해당 세율
SELL_TAX_TABLE = [
    ('2025-01-01', 0.0015),
    ('2024-01-01', 0.0018),
    ('2023-01-01', 0.0020),
    ('0000-01-01', 0.0023),  # 그 이전
]

# 호가단위 표 (상한 미만, 단위) — 2023.1 개편 기준. 오름차순 상한.
TICK_TABLE = [
    (2_000, 1),
    (5_000, 5),
    (20_000, 10),
    (50_000, 50),
    (200_000, 100),
    (500_000, 500),
    (10 ** 12, 1_000),
]
