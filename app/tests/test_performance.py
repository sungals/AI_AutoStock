"""모의 포트폴리오 성과·추적오차 기록 검증 (오프라인)."""
import db_core
import db_portfolio
import performance


def _pf(tmp_path, cash=1_000_000):
    dbp = str(tmp_path / 'q.db')
    db_core.init_db(dbp)
    with db_core.get_connection(dbp) as conn:
        pid = db_portfolio.create_live_portfolio(
            conn, 'p', initial_capital=cash, mode='mock')
        # 보유 10주 @ 10000 (cash 900,000)
        db_portfolio.record_live_trade(conn, pid, 'A', '2026-06-19', 'buy', 10, 10000)
        db_portfolio.update_live_cash(conn, pid, -100000)
        # KOSPI 벤치마크 시세
        for d, px in (('2026-06-19', 3000.0), ('2026-06-20', 3030.0),
                      ('2026-06-21', 2999.7)):
            conn.execute("INSERT INTO macro_prices (symbol, trade_date, close) "
                         "VALUES ('KS11',?,?)", (d, px))
    return dbp, pid


def test_first_snapshot_no_daily_return(tmp_path):
    dbp, pid = _pf(tmp_path)
    price = {'A': 10000}
    with db_core.get_connection(dbp) as conn:
        s = performance.snapshot(conn, pid, '2026-06-19', lambda c: price.get(c))
    assert s['portfolio_value'] == 1_000_000        # 900,000 + 10×10000
    assert s['daily_return'] is None                 # 첫날
    assert abs(s['cum_return'] - 0.0) < 1e-9


def test_second_snapshot_computes_returns(tmp_path):
    dbp, pid = _pf(tmp_path)
    price = {'A': 10000}
    with db_core.get_connection(dbp) as conn:
        performance.snapshot(conn, pid, '2026-06-19', lambda c: price.get(c))
        price['A'] = 11000                            # +10%
        s = performance.snapshot(conn, pid, '2026-06-20', lambda c: price.get(c))
    # 평가 900,000 + 110,000 = 1,010,000 → 전일 대비 +1%
    assert abs(s['portfolio_value'] - 1_010_000) < 1
    assert abs(s['daily_return'] - 0.01) < 1e-6
    assert abs(s['cum_return'] - 0.01) < 1e-6
    # 벤치마크 3000→3030 = +1% → 액티브 ≈ 0
    assert abs(s['benchmark_daily_return'] - 0.01) < 1e-6
    assert abs(s['active_daily_return']) < 1e-6


def test_tracking_error_and_summary(tmp_path):
    dbp, pid = _pf(tmp_path)
    price = {'A': 10000}
    with db_core.get_connection(dbp) as conn:
        performance.snapshot(conn, pid, '2026-06-19', lambda c: price.get(c))
        price['A'] = 11000                            # port +1%, bench +1% → active 0
        performance.snapshot(conn, pid, '2026-06-20', lambda c: price.get(c))
        price['A'] = 13000                            # port +1.98%, bench -1.0% → active +
        performance.snapshot(conn, pid, '2026-06-21', lambda c: price.get(c))

        te = performance.tracking_error(conn, pid)
        summary = performance.performance_summary(conn, pid)

    assert te['n'] == 2 and te['tracking_error'] is not None and te['tracking_error'] > 0
    assert summary['days'] == 3
    assert summary['cum_return'] is not None
    assert 'benchmark_cum_return' in summary and 'active_return' in summary
    assert summary['mdd'] >= 0


def test_tracking_error_insufficient_data(tmp_path):
    dbp, pid = _pf(tmp_path)
    with db_core.get_connection(dbp) as conn:
        performance.snapshot(conn, pid, '2026-06-19', lambda c: 10000)
        te = performance.tracking_error(conn, pid)
    assert te['tracking_error'] is None and te['n'] == 0


def test_snapshot_idempotent_same_date(tmp_path):
    dbp, pid = _pf(tmp_path)
    with db_core.get_connection(dbp) as conn:
        performance.snapshot(conn, pid, '2026-06-19', lambda c: 10000)
        performance.snapshot(conn, pid, '2026-06-19', lambda c: 10000)   # 재실행
        n = conn.execute(
            "SELECT COUNT(*) c FROM live_performance WHERE portfolio_id=?",
            (pid,)).fetchone()['c']
    assert n == 1                                     # 같은 날 1행(멱등)
