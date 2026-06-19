"""Task 6: backtester가 (1) 비용 적용 시 CAGR이 낮아지고 (2) PIT 게이트를 경유하는지."""
from datetime import date, timedelta
import numpy as np
import pytest

import db_core
import backtester


def _trading_dates(start: str, n: int):
    d = date.fromisoformat(start)
    out = []
    while len(out) < n:
        if d.weekday() < 5:        # 평일만
            out.append(d.isoformat())
        d += timedelta(days=1)
    return out


def _seed(dbp):
    db_core.init_db(dbp)
    rng = np.random.default_rng(42)
    dates = _trading_dates('2022-01-03', 260)
    # 8개 종목: 일부는 상승추세, 일부는 하락추세 (모멘텀이 구분 가능하도록)
    drifts = [0.0015, 0.0012, 0.0009, 0.0005, -0.0003, -0.0008, 0.0011, -0.0011]
    with db_core.get_connection(dbp) as conn:
        for i, drift in enumerate(drifts):
            code = '%06d' % (i + 1)
            conn.execute(
                "INSERT INTO companies (corp_code, stock_code, corp_name) VALUES (?,?,?)",
                ('C%06d' % i, code, 'CO%d' % i))
            price = 10000.0
            for dt in dates:
                ret = drift + rng.normal(0, 0.01)
                price *= (1 + ret)
                px = int(price)
                vol = 200000
                conn.execute(
                    """INSERT INTO price_data
                       (stock_code, trade_date, open, high, low, close, volume, market_cap, value)
                       VALUES (?,?,?,?,?,?,?,?,?)""",
                    (code, dt, px, int(px * 1.01), int(px * 0.99), px, vol,
                     px * 1_000_000, px * vol))
    return dates


def test_costs_reduce_reported_cagr(tmp_path):
    dbp = str(tmp_path / 'q.db')
    dates = _seed(dbp)
    with db_core.get_connection(dbp) as conn:
        res_ideal = backtester.run_backtest(
            conn, 'momentum', dates[40], dates[-1], top_n=3, fill_model='ideal')
        res_real = backtester.run_backtest(
            conn, 'momentum', dates[40], dates[-1], top_n=3, fill_model='realistic')
    assert res_real['n_trades'] > 0
    assert res_real['cagr'] <= res_ideal['cagr']     # 신뢰성 적용 = 보수화


def test_backtest_uses_pit_metrics(tmp_path, monkeypatch):
    dbp = str(tmp_path / 'q.db')
    dates = _seed(dbp)
    calls = {'n': 0}
    import point_in_time
    real_fn = point_in_time.get_metrics_asof

    def spy(conn, corp_code, as_of_date, stock_code=None):
        calls['n'] += 1
        return real_fn(conn, corp_code, as_of_date, stock_code)

    monkeypatch.setattr(backtester.point_in_time, 'get_metrics_asof', spy)
    with db_core.get_connection(dbp) as conn:
        backtester.run_backtest(conn, 'momentum', dates[40], dates[-1],
                                top_n=3, fill_model='realistic')
    assert calls['n'] > 0       # PIT 게이트를 실제로 경유
