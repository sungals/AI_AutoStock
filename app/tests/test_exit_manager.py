"""청산(매도/손절) 로직 검증 (오프라인, 인메모리 브로커)."""
import db_core
import db_portfolio
import exit_manager
import risk_guard
import portfolio_operations as ops
from broker.memory import MemoryBroker


def _pf(tmp_path, cash=10_000_000):
    dbp = str(tmp_path / 'q.db')
    db_core.init_db(dbp)
    with db_core.get_connection(dbp) as conn:
        pid = db_portfolio.create_live_portfolio(
            conn, 'p', initial_capital=cash, mode='mock')
    return dbp, pid


def _buy(conn, pid, code, qty, price, date_):
    db_portfolio.record_live_trade(conn, pid, code, date_, 'buy', qty, price,
                                   metadata={'reason': 'test'})
    db_portfolio.update_live_cash(conn, pid, -qty * price)


# ── 순수함수 ──

def test_check_stop_loss():
    assert ops.check_stop_loss(10000, 9000, 0.10) is True     # -10%
    assert ops.check_stop_loss(10000, 9500, 0.10) is False    # -5%


# ── 청산 규칙 ──

def test_hard_stop_loss_sells(tmp_path):
    dbp, pid = _pf(tmp_path)
    with db_core.get_connection(dbp) as conn:
        _buy(conn, pid, 'A', 10, 10000, '2026-06-20')
    brk = MemoryBroker(prices={'A': 8900})            # -11% → 손절
    brk.positions['A'] = 10
    with db_core.get_connection(dbp) as conn:
        res = exit_manager.run_exits(conn, pid, brk, trade_date='2026-06-21',
                                     stop_loss_pct=0.10)
        holdings = db_portfolio.get_live_holdings(conn, pid)
    assert res['sold'] == 1 and res['exits'][0]['reason'] == 'stop_loss'
    assert 'A' not in holdings                          # 전량 매도됨
    assert brk.positions.get('A', 0) == 0


def test_trailing_stop_sells(tmp_path):
    dbp, pid = _pf(tmp_path)
    with db_core.get_connection(dbp) as conn:
        _buy(conn, pid, 'A', 10, 10000, '2026-06-01')
        # price_data로 최고가 13000 형성 후 현재 11800 (최고가 대비 -9.2%)
        for d, px in (('2026-06-02', 13000), ('2026-06-21', 11800)):
            conn.execute("INSERT INTO price_data (stock_code, trade_date, high, close) "
                         "VALUES ('A',?,?,?)", (d, px, px))
    brk = MemoryBroker(prices={'A': 11800})
    brk.positions['A'] = 10
    with db_core.get_connection(dbp) as conn:
        res = exit_manager.run_exits(conn, pid, brk, trade_date='2026-06-21',
                                     stop_loss_pct=0.20, trail_pct=0.08)
    assert res['sold'] == 1 and res['exits'][0]['reason'] == 'trailing_stop'


def test_timeout_sells(tmp_path):
    dbp, pid = _pf(tmp_path)
    with db_core.get_connection(dbp) as conn:
        _buy(conn, pid, 'A', 10, 10000, '2026-01-01')   # 보유 170일 이상
    brk = MemoryBroker(prices={'A': 10000})
    brk.positions['A'] = 10
    with db_core.get_connection(dbp) as conn:
        res = exit_manager.run_exits(conn, pid, brk, trade_date='2026-06-21',
                                     stop_loss_pct=0.20, trail_pct=0.20,
                                     max_hold_days=90)
    assert res['sold'] == 1 and res['exits'][0]['reason'] == 'timeout'


def test_no_trigger_holds(tmp_path):
    dbp, pid = _pf(tmp_path)
    with db_core.get_connection(dbp) as conn:
        _buy(conn, pid, 'A', 10, 10000, '2026-06-20')
    brk = MemoryBroker(prices={'A': 10100})             # +1%
    brk.positions['A'] = 10
    with db_core.get_connection(dbp) as conn:
        res = exit_manager.run_exits(conn, pid, brk, trade_date='2026-06-21')
        holdings = db_portfolio.get_live_holdings(conn, pid)
    assert res['sold'] == 0 and res['held'] == 1
    assert holdings['A'] == 10


def test_exit_records_pnl_and_updates_cash(tmp_path):
    dbp, pid = _pf(tmp_path, cash=10_000_000)
    with db_core.get_connection(dbp) as conn:
        _buy(conn, pid, 'A', 10, 10000, '2026-06-20')    # 매수 후 현금 9,900,000
    brk = MemoryBroker(prices={'A': 8900})
    brk.positions['A'] = 10
    with db_core.get_connection(dbp) as conn:
        res = exit_manager.run_exits(conn, pid, brk, trade_date='2026-06-21',
                                     stop_loss_pct=0.10)
        pf = db_portfolio.get_live_portfolio(conn, pid)
    assert res['exits'][0]['pnl_pct'] == -11.0           # (8900-10000)/10000
    assert abs(pf['cash'] - (9_900_000 + 10 * 8900)) < 1  # 매도대금 환입


def test_exits_allowed_even_when_kill_switch_tripped(tmp_path):
    """킬스위치가 켜져 있어도 청산(손절)은 허용되어야 한다(리스크 축소)."""
    dbp, pid = _pf(tmp_path)
    with db_core.get_connection(dbp) as conn:
        _buy(conn, pid, 'A', 10, 10000, '2026-06-20')
        risk_guard.trip_kill_switch(conn, pid, '비상정지')
    brk = MemoryBroker(prices={'A': 8500})
    brk.positions['A'] = 10
    with db_core.get_connection(dbp) as conn:
        res = exit_manager.run_exits(conn, pid, brk, trade_date='2026-06-21',
                                     stop_loss_pct=0.10)
    assert res['sold'] == 1                              # 킬스위치와 무관하게 손절 실행
