"""킬스위치 + 일일 손실한도 집행 검증 (오프라인)."""
import db_core
import db_portfolio
import risk_guard
import paper_trader
import config
from broker.memory import MemoryBroker


def _pf(tmp_path, cash=1_000_000, limit=0.03):
    dbp = str(tmp_path / 'q.db')
    db_core.init_db(dbp)
    with db_core.get_connection(dbp) as conn:
        pid = db_portfolio.create_live_portfolio(
            conn, 'p', initial_capital=cash, mode='mock', daily_loss_limit=limit)
    return dbp, pid


def _hold(conn, pid, code, qty, price):
    db_portfolio.record_live_trade(conn, pid, code, '2026-06-21', 'buy', qty, price)
    db_portfolio.update_live_cash(conn, pid, -qty * price)


# ── 킬스위치 ──

def test_global_config_kill_switch_blocks(tmp_path, monkeypatch):
    dbp, pid = _pf(tmp_path)
    monkeypatch.setattr(config, 'TRADING_KILL_SWITCH', True)
    with db_core.get_connection(dbp) as conn:
        g = risk_guard.pre_trade_check(conn, pid, lambda c: 100, '2026-06-21')
    assert g['allowed'] is False and '전역' in g['reason']


def test_per_portfolio_trip_and_reset(tmp_path):
    dbp, pid = _pf(tmp_path)
    with db_core.get_connection(dbp) as conn:
        risk_guard.trip_kill_switch(conn, pid, '수동 정지')
        assert risk_guard.is_halted(conn, pid)[0] is True
        risk_guard.reset_kill_switch(conn, pid)
        assert risk_guard.is_halted(conn, pid)[0] is False


def test_global_db_halt_blocks_any_portfolio(tmp_path):
    dbp, pid = _pf(tmp_path)
    with db_core.get_connection(dbp) as conn:
        risk_guard.trip_kill_switch(conn, 0, '비상')        # portfolio_id=0 전역
        halted, reason = risk_guard.is_halted(conn, pid)
    assert halted is True and '전역' in reason


# ── 일일 손실한도 ──

def test_daily_loss_within_limit_allowed(tmp_path):
    dbp, pid = _pf(tmp_path)        # 한도 3%
    with db_core.get_connection(dbp) as conn:
        _hold(conn, pid, 'A', 10, 10000)               # cash 900,000 + 보유 10주
        price = {'A': 10000}
        pf = lambda c: price.get(c)
        assert risk_guard.pre_trade_check(conn, pid, pf, '2026-06-21')['allowed']  # start=1,000,000
        price['A'] = 9000                              # 평가 990,000 → 손실 1%
        assert risk_guard.pre_trade_check(conn, pid, pf, '2026-06-21')['allowed']


def test_daily_loss_exceeded_trips_and_persists(tmp_path):
    dbp, pid = _pf(tmp_path)
    with db_core.get_connection(dbp) as conn:
        _hold(conn, pid, 'A', 10, 10000)
        price = {'A': 10000}
        pf = lambda c: price.get(c)
        risk_guard.pre_trade_check(conn, pid, pf, '2026-06-21')   # start 1,000,000
        price['A'] = 6000                              # 평가 960,000 → 손실 4% ≥ 3%
        g = risk_guard.pre_trade_check(conn, pid, pf, '2026-06-21')
        assert g['allowed'] is False and '손실한도' in g['reason']
        price['A'] = 10000                             # 가격 회복해도
        assert risk_guard.pre_trade_check(conn, pid, pf, '2026-06-21')['allowed'] is False


# ── 페이퍼 트레이더 연동 ──

def test_paper_trader_respects_halt(tmp_path):
    dbp, pid = _pf(tmp_path, cash=10_000_000)
    brk = MemoryBroker(prices={'005930': 70000})
    with db_core.get_connection(dbp) as conn:
        risk_guard.trip_kill_switch(conn, pid, '테스트 정지')
        res = paper_trader.run_paper_session(conn, pid, ['005930'], broker=brk,
                                             trade_date='2026-06-21')
    assert res.get('halted') is True and res['submitted'] == 0
    assert brk.positions == {}                         # 주문이 나가지 않음
