"""거시 데이터 수집/저장 + 시장 국면 감지.

05-구현-가이드 Phase 6. yfinance는 선택 의존성으로 처리하고, 테스트/운영 안정성을 위해
fetch 함수를 주입할 수 있다. Python 3.9 호환.
"""
from typing import Callable, Dict, List, Optional, Tuple


MACRO_SYMBOLS = {
    'CL=F': ('WTI 원유', 'commodity'),
    'GC=F': ('금', 'commodity'),
    'USDKRW=X': ('달러/원', 'forex'),
    'BTC-USD': ('비트코인', 'crypto'),
    '^VIX': ('VIX', 'index'),
    'KS11': ('KOSPI', 'index'),
}


def upsert_macro_price(conn, symbol: str, name_ko: str, category: str,
                       trade_date: str, close: float,
                       change_pct: float) -> None:
    conn.execute(
        """INSERT OR REPLACE INTO macro_prices
           (symbol, name_ko, category, trade_date, close, change_pct)
           VALUES (?,?,?,?,?,?)""",
        (symbol, name_ko, category, trade_date, close, change_pct))


def _fetch_yfinance(symbol: str) -> List[Dict]:
    try:
        import yfinance as yf
    except Exception:
        return []

    yf_symbol = '^KS11' if symbol == 'KS11' else symbol
    df = yf.download(yf_symbol, period='5d', progress=False)
    if df is None or df.empty:
        return []
    rows = []
    for idx, r in df.iterrows():
        close = r.get('Close')
        if hasattr(close, 'iloc'):
            close = close.iloc[0]
        try:
            close = float(close)
        except Exception:
            continue
        rows.append({'trade_date': idx.strftime('%Y-%m-%d'), 'close': close})
    return rows


def fetch_macro_data(conn, symbols: Optional[Dict[str, Tuple[str, str]]] = None,
                     fetch_fn: Optional[Callable[[str], List[Dict]]] = None) -> Dict:
    """글로벌 매크로 데이터를 수집해 최신 행을 저장한다."""
    symbol_map = symbols or MACRO_SYMBOLS
    fetch = fetch_fn or _fetch_yfinance
    result = {'symbols': 0, 'rows': 0, 'skipped': False}
    for symbol, (name_ko, category) in symbol_map.items():
        rows = fetch(symbol)
        if len(rows) < 1:
            continue
        last = rows[-1]
        prev = rows[-2] if len(rows) >= 2 else last
        close = float(last['close'])
        prev_close = float(prev['close'])
        change_pct = ((close - prev_close) / prev_close * 100.0) if prev_close else 0.0
        upsert_macro_price(
            conn, symbol, name_ko, category, last['trade_date'], close, round(change_pct, 4))
        result['symbols'] += 1
        result['rows'] += 1
    if result['rows'] == 0 and fetch_fn is None:
        result['skipped'] = True
        result['reason'] = 'yfinance 없음 또는 데이터 없음'
    return result


def detect_market_regime(conn) -> str:
    """KOSPI 60일 추세 + VIX로 시장 국면을 감지한다."""
    rows = conn.execute(
        """SELECT close FROM macro_prices
           WHERE symbol='KS11'
           ORDER BY trade_date DESC LIMIT 60""").fetchall()
    if not rows or len(rows) < 20:
        return 'sideways'
    closes = [float(r['close']) for r in rows if r['close'] is not None]
    if len(closes) < 20 or closes[-1] <= 0:
        return 'sideways'
    recent_close = closes[0]
    close_60d = closes[-1]
    pct_change_60d = (recent_close - close_60d) / close_60d * 100.0

    vix_row = conn.execute(
        """SELECT close FROM macro_prices
           WHERE symbol='^VIX'
           ORDER BY trade_date DESC LIMIT 1""").fetchone()
    vix = float(vix_row['close']) if vix_row and vix_row['close'] is not None else 20.0

    if pct_change_60d > 5.0 and vix < 25.0:
        return 'bull'
    if pct_change_60d < -5.0 or vix > 30.0:
        return 'bear'
    return 'sideways'
