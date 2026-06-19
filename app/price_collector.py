"""주가 수집 (pykrx) → price_data 테이블.

OHLCV + 시가총액 + 거래대금을 일자별로 수집한다. API 키 불필요.
fetch 함수를 주입할 수 있어 네트워크 없이 테스트 가능.
03-시스템-아키텍처.md, 02-외부-API-가이드.md §8. Python 3.9 호환.
"""
from typing import List, Dict, Optional, Callable
import config
from rate_limit import rate_limited


@rate_limited(config.PYKRX_DELAY)
def _fetch_price_rows(stock_code: str, start: str, end: str) -> List[Dict]:
    """pykrx로 한 종목의 OHLCV + 시가총액 + 거래대금을 정규화 행 리스트로 반환.

    start/end: 'YYYYMMDD'. 반환 각 행 키:
    trade_date('YYYY-MM-DD'), open, high, low, close, volume, market_cap, value
    """
    from pykrx import stock
    ohlcv = stock.get_market_ohlcv_by_date(start, end, stock_code)
    try:
        cap = stock.get_market_cap_by_date(start, end, stock_code)
    except Exception:
        cap = None

    rows = []  # type: List[Dict]
    for idx in ohlcv.index:
        r = ohlcv.loc[idx]
        trade_date = idx.strftime('%Y-%m-%d')
        close = int(r.get('종가', 0) or 0)
        volume = int(r.get('거래량', 0) or 0)
        market_cap = None
        value = None
        if cap is not None and idx in cap.index:
            cr = cap.loc[idx]
            market_cap = int(cr.get('시가총액', 0) or 0) or None
            value = int(cr.get('거래대금', 0) or 0) or None
        if value is None:
            value = close * volume
        rows.append({
            'trade_date': trade_date,
            'open': int(r.get('시가', 0) or 0),
            'high': int(r.get('고가', 0) or 0),
            'low': int(r.get('저가', 0) or 0),
            'close': close,
            'volume': volume,
            'market_cap': market_cap,
            'value': value,
        })
    return rows


def upsert_prices(conn, stock_code: str, rows: List[Dict]) -> int:
    """정규화된 가격 행들을 price_data에 멱등 저장."""
    n = 0
    for row in rows:
        conn.execute(
            """INSERT OR REPLACE INTO price_data
               (stock_code, trade_date, open, high, low, close, volume, market_cap, value)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (stock_code, row['trade_date'], row['open'], row['high'], row['low'],
             row['close'], row['volume'], row.get('market_cap'), row.get('value')))
        n += 1
    return n


def collect_prices(conn, stock_codes: List[str], start: str, end: str,
                   fetch_fn: Optional[Callable] = None) -> Dict:
    """여러 종목의 가격을 수집·저장. start/end: 'YYYYMMDD'.

    fetch_fn 주입 시 네트워크 없이 테스트 가능 (기본: pykrx).
    """
    fetch = fetch_fn or _fetch_price_rows
    result = {'stocks': 0, 'rows': 0, 'failed': 0}
    for code in stock_codes:
        try:
            rows = fetch(code, start, end)
        except Exception:
            result['failed'] += 1
            continue
        result['rows'] += upsert_prices(conn, code, rows)
        result['stocks'] += 1
    return result
