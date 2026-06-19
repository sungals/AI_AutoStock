"""Phase 9: 포트폴리오 관리와 리스크 가드."""
import db_core
import kelly_criterion
import portfolio_operations as po
import db_portfolio


def test_calculate_kelly_ratio_fractional_and_capped():
    assert kelly_criterion.calculate_kelly_ratio(0.6, 0.12, 0.06) == 0.1
    assert kelly_criterion.calculate_kelly_ratio(0.9, 0.50, 0.05) == 0.2225
    assert kelly_criterion.calculate_kelly_ratio(0.9, 0.50, 0.05, fraction=1.0) == 0.3
    assert kelly_criterion.calculate_kelly_ratio(0.4, 0.05, 0.10) == 0.0
    assert kelly_criterion.calculate_kelly_ratio(0.6, 0.10, 0.0) == 0.0


def test_portfolio_risk_guards():
    assert po.check_trailing_stop(1000, 1200, 1090, trail_pct=0.08) is True
    assert po.check_trailing_stop(1000, 1200, 1120, trail_pct=0.08) is False
    assert po.check_timeout_exit('2024-01-01', '2024-04-01', max_days=90) is True
    assert po.check_vix_defensive(31.0) is True
    assert po.check_daily_loss_limit(-31000, 1000000, limit_pct=0.03) is True


def test_virtual_portfolio_create_trade_and_value(tmp_path):
    dbp = str(tmp_path / 'q.db')
    db_core.init_db(dbp)
    with db_core.get_connection(dbp) as conn:
        pid = db_portfolio.create_virtual_portfolio(
            conn, '테스트', strategy='fusion', initial_capital=1_000_000)
        db_portfolio.record_virtual_trade(
            conn, pid, '000001', '2024-01-02', 'buy', 10, 10000, reason='BUY')
        conn.execute(
            """INSERT INTO price_data (stock_code, trade_date, close)
               VALUES ('000001', '2024-01-03', 11000)""")
        value = db_portfolio.calculate_virtual_value(conn, pid, '2024-01-03')
        db_portfolio.save_virtual_performance(conn, pid, '2024-01-03', value)
        row = conn.execute(
            "SELECT cash FROM virtual_portfolios WHERE id=?", (pid,)).fetchone()
        perf = conn.execute(
            "SELECT portfolio_value, total_return FROM virtual_performance WHERE portfolio_id=?",
            (pid,)).fetchone()

    assert row['cash'] == 900000
    assert value == 1_010_000
    assert perf['portfolio_value'] == 1_010_000
    assert perf['total_return'] == 1.0


def test_live_portfolio_risk_allows_mock_only_by_default(tmp_path):
    dbp = str(tmp_path / 'q.db')
    db_core.init_db(dbp)
    with db_core.get_connection(dbp) as conn:
        pid = db_portfolio.create_live_portfolio(
            conn, 'mock-live', initial_capital=2_000_000, mode='mock')
        row = db_portfolio.get_live_portfolio(conn, pid)

    assert row['mode'] == 'mock'
    assert row['cash'] == 2_000_000
