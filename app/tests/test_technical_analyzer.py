"""Phase 3: 기술지표 계산 + technical_signals 저장."""
from datetime import date, timedelta

import pandas as pd

import db_core
import technical_analyzer as ta


def _price_frame(n=220):
    rows = []
    d = date(2024, 1, 2)
    price = 10000.0
    for i in range(n):
        price += 35 + (i % 7)
        close = int(price)
        rows.append({
            'trade_date': d.isoformat(),
            'open': close - 20,
            'high': close + 120,
            'low': close - 100,
            'close': close,
            'volume': 100000 + i * 100,
        })
        d += timedelta(days=1)
    return pd.DataFrame(rows)


def test_calculate_technical_signals_core_indicators():
    signals = ta.calculate_technical_signals('000001', _price_frame())

    for name in ('ma_5', 'ma_20', 'ma_60', 'ma_120', 'ma_200',
                 'ma_cross', 'macd', 'rsi_14', 'bollinger', 'atr_14', 'obv'):
        assert name in signals
        assert signals[name][0] is not None
        assert isinstance(signals[name][1], str)

    assert signals['ma_5'][0] > signals['ma_20'][0]
    assert signals['rsi_14'][0] > 50


def test_detect_candlestick_patterns():
    hammer_df = pd.DataFrame([
        {'open': 100, 'high': 103, 'low': 99, 'close': 101},
        {'open': 100, 'high': 106, 'low': 70, 'close': 105},
    ])
    assert 'hammer' in ta.detect_candlestick_patterns(hammer_df)

    engulf_df = pd.DataFrame([
        {'open': 110, 'high': 112, 'low': 95, 'close': 100},
        {'open': 98, 'high': 118, 'low': 96, 'close': 115},
    ])
    assert 'bullish_engulfing' in ta.detect_candlestick_patterns(engulf_df)


def test_calculate_and_save_technical_signals(tmp_path):
    dbp = str(tmp_path / 'q.db')
    db_core.init_db(dbp)
    df = _price_frame(80)
    with db_core.get_connection(dbp) as conn:
        conn.execute(
            "INSERT INTO companies (corp_code, stock_code, corp_name) VALUES (?,?,?)",
            ('C1', '000001', 'CO1'))
        for r in df.to_dict('records'):
            conn.execute(
                """INSERT INTO price_data
                   (stock_code, trade_date, open, high, low, close, volume)
                   VALUES (?,?,?,?,?,?,?)""",
                ('000001', r['trade_date'], r['open'], r['high'],
                 r['low'], r['close'], r['volume']))
        count = ta.calculate_for_stock(conn, '000001')

    with db_core.get_connection(dbp) as conn:
        rows = conn.execute(
            "SELECT signal_name, signal_label FROM technical_signals "
            "WHERE stock_code='000001'").fetchall()

    assert count >= 8
    names = {r['signal_name'] for r in rows}
    assert {'ma_20', 'macd', 'rsi_14', 'bollinger', 'atr_14', 'obv'} <= names
    assert all(r['signal_label'] for r in rows)
