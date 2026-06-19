"""기술적 분석 — MA/MACD/RSI/Bollinger/ATR/OBV + 캔들 패턴.

05-구현-가이드 Phase 3의 12종 기술지표 중 현재 데이터로 계산 가능한 핵심 지표를
pandas 기반으로 구현한다. 외부 ta 패키지 없이 동작한다. Python 3.9 호환.
"""
from typing import Dict, List, Optional, Tuple

import pandas as pd


SignalMap = Dict[str, Tuple[Optional[float], Optional[str]]]


def _clean_df(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    if 'trade_date' in out.columns:
        out = out.sort_values('trade_date')
    for col in ('open', 'high', 'low', 'close'):
        out[col] = pd.to_numeric(out[col], errors='coerce')
    if 'volume' in out.columns:
        out['volume'] = pd.to_numeric(out['volume'], errors='coerce')
    return out.dropna(subset=['open', 'high', 'low', 'close'])


def _last_float(series: pd.Series) -> Optional[float]:
    if series.empty or pd.isna(series.iloc[-1]):
        return None
    return float(series.iloc[-1])


def _rsi(close: pd.Series, window: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1.0 / window, adjust=False, min_periods=window).mean()
    avg_loss = loss.ewm(alpha=1.0 / window, adjust=False, min_periods=window).mean()
    rs = avg_gain / avg_loss.replace(0, pd.NA)
    rsi = 100.0 - (100.0 / (1.0 + rs))
    return rsi.mask((avg_loss == 0) & (avg_gain > 0), 100.0)


def _atr(df: pd.DataFrame, window: int = 14) -> pd.Series:
    prev_close = df['close'].shift(1)
    tr = pd.concat([
        df['high'] - df['low'],
        (df['high'] - prev_close).abs(),
        (df['low'] - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.rolling(window).mean()


def _obv(close: pd.Series, volume: pd.Series) -> pd.Series:
    direction = close.diff().fillna(0).apply(lambda x: 1 if x > 0 else (-1 if x < 0 else 0))
    return (direction * volume.fillna(0)).cumsum()


def calculate_technical_signals(stock_code: str, df: pd.DataFrame) -> SignalMap:
    """OHLCV DataFrame(오름차순 또는 trade_date 포함)을 기술지표 dict로 변환."""
    data = _clean_df(df)
    if data.empty:
        return {}

    close = data['close']
    high = data['high']
    low = data['low']
    volume = data['volume'] if 'volume' in data.columns else pd.Series([0] * len(data))
    results = {}  # type: SignalMap

    for period in (5, 20, 60, 120, 200):
        if len(data) >= period:
            val = _last_float(close.rolling(period).mean())
            if val is not None:
                results['ma_%d' % period] = (round(val, 4), 'MA%d=%.0f' % (period, val))

    if len(data) >= 21:
        ma5 = close.rolling(5).mean()
        ma20 = close.rolling(20).mean()
        curr_5, curr_20 = ma5.iloc[-1], ma20.iloc[-1]
        prev_5, prev_20 = ma5.iloc[-2], ma20.iloc[-2]
        if curr_5 > curr_20 and prev_5 <= prev_20:
            results['ma_cross'] = (1.0, '골든크로스')
        elif curr_5 < curr_20 and prev_5 >= prev_20:
            results['ma_cross'] = (-1.0, '데드크로스')
        else:
            results['ma_cross'] = (0.0, '보합')

    if len(data) >= 35:
        ema12 = close.ewm(span=12, adjust=False).mean()
        ema26 = close.ewm(span=26, adjust=False).mean()
        macd = ema12 - ema26
        signal = macd.ewm(span=9, adjust=False).mean()
        hist = macd - signal
        val = _last_float(macd)
        if val is not None:
            label = 'MACD 골든크로스' if hist.iloc[-1] > 0 else 'MACD 데드크로스'
            results['macd'] = (round(val, 4), label)

    if len(data) >= 15:
        val = _last_float(_rsi(close, 14))
        if val is not None:
            if val <= 30:
                label = 'RSI 과매도 (%.0f)' % val
            elif val >= 70:
                label = 'RSI 과매수 (%.0f)' % val
            else:
                label = 'RSI 중립 (%.0f)' % val
            results['rsi_14'] = (round(val, 4), label)

    if len(data) >= 20:
        mid = close.rolling(20).mean()
        std = close.rolling(20).std(ddof=0)
        lower = mid - 2 * std
        upper = mid + 2 * std
        curr_close = float(close.iloc[-1])
        if curr_close <= float(lower.iloc[-1]):
            label = '볼린저 하단 이탈 (과매도)'
        elif curr_close >= float(upper.iloc[-1]):
            label = '볼린저 상단 이탈 (과매수)'
        else:
            label = '볼린저 밴드 내'
        results['bollinger'] = (round(curr_close, 4), label)

    if len(data) >= 15:
        val = _last_float(_atr(data, 14))
        if val is not None:
            results['atr_14'] = (round(val, 4), 'ATR=%.0f' % val)

    if len(data) >= 5:
        val = _last_float(_obv(close, volume))
        if val is not None:
            results['obv'] = (round(val, 4), 'OBV=%.0f' % val)

    results.update(detect_candlestick_patterns(data))
    return results


def detect_candlestick_patterns(df: pd.DataFrame) -> SignalMap:
    """망치형, 도지, 상승장악형, 유성형을 감지한다."""
    data = _clean_df(df)
    if len(data) < 2:
        return {}

    r = data.iloc[-1]
    p = data.iloc[-2]
    body = abs(float(r['close']) - float(r['open']))
    upper_shadow = float(r['high']) - max(float(r['close']), float(r['open']))
    lower_shadow = min(float(r['close']), float(r['open'])) - float(r['low'])
    body_base = max(body, 1e-9)

    results = {}  # type: SignalMap
    if lower_shadow > body_base * 2 and upper_shadow < body_base * 0.5 and r['close'] > r['open']:
        results['hammer'] = (1.0, '망치형 (반등 신호)')

    atr_approx = (data['high'] - data['low']).rolling(14, min_periods=1).mean().iloc[-1]
    if body < float(atr_approx) * 0.1:
        results['doji'] = (1.0, '도지 (방향 전환 신호)')

    if (p['close'] < p['open'] and r['close'] > r['open'] and
            r['open'] < p['close'] and r['close'] > p['open']):
        results['bullish_engulfing'] = (1.0, '상승장악형 (강한 반등 신호)')

    if upper_shadow > body_base * 2 and lower_shadow < body_base * 0.5 and r['close'] < r['open']:
        results['shooting_star'] = (-1.0, '유성형 (하락 신호)')

    return results


def load_price_frame(conn, stock_code: str, end_date: Optional[str] = None,
                     limit: int = 500) -> pd.DataFrame:
    """DB price_data에서 최근 OHLCV를 DataFrame으로 로드한다."""
    if end_date is None:
        rows = conn.execute(
            """SELECT trade_date, open, high, low, close, volume
               FROM price_data WHERE stock_code=?
               ORDER BY trade_date DESC LIMIT ?""",
            (stock_code, limit)).fetchall()
    else:
        rows = conn.execute(
            """SELECT trade_date, open, high, low, close, volume
               FROM price_data WHERE stock_code=? AND trade_date<=?
               ORDER BY trade_date DESC LIMIT ?""",
            (stock_code, end_date, limit)).fetchall()
    return pd.DataFrame([dict(r) for r in reversed(rows)])


def save_technical_signals(conn, stock_code: str, calc_date: str,
                           signals: SignalMap) -> int:
    """technical_signals 테이블에 계산 결과를 멱등 저장한다."""
    n = 0
    for name, (value, label) in signals.items():
        conn.execute(
            """INSERT OR REPLACE INTO technical_signals
               (stock_code, calc_date, signal_name, signal_value, signal_label)
               VALUES (?,?,?,?,?)""",
            (stock_code, calc_date, name, value, label))
        n += 1
    return n


def calculate_for_stock(conn, stock_code: str, end_date: Optional[str] = None,
                        limit: int = 500) -> int:
    """단일 종목 기술지표를 계산해 저장하고 저장 행 수를 반환한다."""
    df = load_price_frame(conn, stock_code, end_date=end_date, limit=limit)
    if df.empty:
        return 0
    calc_date = str(df.iloc[-1]['trade_date'])
    signals = calculate_technical_signals(stock_code, df)
    return save_technical_signals(conn, stock_code, calc_date, signals)


def calculate_all(conn, end_date: Optional[str] = None, limit: int = 500) -> Dict[str, int]:
    """companies 전체 종목의 기술지표를 계산한다."""
    rows = conn.execute("SELECT stock_code FROM companies ORDER BY stock_code").fetchall()
    result = {}
    for r in rows:
        code = r['stock_code']
        result[code] = calculate_for_stock(conn, code, end_date=end_date, limit=limit)
    return result
