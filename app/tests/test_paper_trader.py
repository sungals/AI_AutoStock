"""페이퍼 트레이딩 루프 — 인메모리 브로커로 결정적 검증(네트워크 없음)."""
import db_core
import db_portfolio
import paper_trader
from broker.memory import MemoryBroker


def _setup(tmp_path, cash=10_000_000, max_pos=0.2):
    dbp = str(tmp_path / 'q.db')
    db_core.init_db(dbp)
    with db_core.get_connection(dbp) as conn:
        pid = db_portfolio.create_live_portfolio(
            conn, 'paper1', initial_capital=cash, mode='mock',
            max_position_size=max_pos)
    return dbp, pid


def test_paper_session_buys_and_records(tmp_path):
    dbp, pid = _setup(tmp_path)
    brk = MemoryBroker(prices={'005930': 70000, '000660': 200000})
    with db_core.get_connection(dbp) as conn:
        res = paper_trader.run_paper_session(
            conn, pid, ['005930', '000660'], broker=brk, trade_date='2026-06-21')
    assert res['submitted'] == 2 and res['failed'] == 0
    with db_core.get_connection(dbp) as conn:
        holdings = db_portfolio.get_live_holdings(conn, pid)
        pf = db_portfolio.get_live_portfolio(conn, pid)
    # 종목당 최대 비중 20% = 200만원 예산. 삼성 70000 → 28주, 하이닉스 200000 → 10주
    assert holdings['005930'] == 28 and holdings['000660'] == 10
    assert pf['cash'] < 10_000_000                 # 현금 차감됨
    assert brk.positions['005930'] == 28           # 브로커 포지션과 일치


def test_idempotent_same_day(tmp_path):
    dbp, pid = _setup(tmp_path)
    brk = MemoryBroker(prices={'005930': 70000})
    with db_core.get_connection(dbp) as conn:
        r1 = paper_trader.run_paper_session(conn, pid, ['005930'], broker=brk,
                                            trade_date='2026-06-21')
        r2 = paper_trader.run_paper_session(conn, pid, ['005930'], broker=brk,
                                            trade_date='2026-06-21')
    assert r1['submitted'] == 1
    assert r2['submitted'] == 0 and r2['skipped'] == 1   # 같은 날 재매수 안 함
    with db_core.get_connection(dbp) as conn:
        assert db_portfolio.get_live_holdings(conn, pid)['005930'] == 28


def test_already_held_skipped(tmp_path):
    dbp, pid = _setup(tmp_path)
    brk = MemoryBroker(prices={'005930': 70000})
    with db_core.get_connection(dbp) as conn:
        paper_trader.run_paper_session(conn, pid, ['005930'], broker=brk,
                                       trade_date='2026-06-20')
        # 다음 날: 이미 보유 중이므로 스킵
        res = paper_trader.run_paper_session(conn, pid, ['005930'], broker=brk,
                                             trade_date='2026-06-21')
    assert res['skipped'] == 1 and res['submitted'] == 0


def test_no_price_fails_gracefully(tmp_path):
    dbp, pid = _setup(tmp_path)
    brk = MemoryBroker(prices={})                  # 가격 없음
    with db_core.get_connection(dbp) as conn:
        res = paper_trader.run_paper_session(conn, pid, ['005930'], broker=brk,
                                             trade_date='2026-06-21')
    assert res['failed'] == 1 and res['submitted'] == 0


def test_requires_mock_portfolio(tmp_path):
    dbp = str(tmp_path / 'q.db')
    db_core.init_db(dbp)
    with db_core.get_connection(dbp) as conn:
        pid = db_portfolio.create_live_portfolio(
            conn, 'livep', initial_capital=1_000_000, mode='live')
        try:
            paper_trader.run_paper_session(conn, pid, ['005930'],
                                           broker=MemoryBroker(prices={'005930': 100}))
            assert False, 'should refuse live portfolio'
        except RuntimeError as e:
            assert 'mock' in str(e)


def test_reconcile_matches_and_detects_mismatch(tmp_path):
    dbp, pid = _setup(tmp_path)
    brk = MemoryBroker(prices={'005930': 70000})
    with db_core.get_connection(dbp) as conn:
        paper_trader.run_paper_session(conn, pid, ['005930'], broker=brk,
                                       trade_date='2026-06-21')
        rec = paper_trader.reconcile(conn, pid, brk)
        assert rec['matched'] is True

        # 브로커 쪽 수량을 인위적으로 틀어 불일치 유발
        brk.positions['005930'] += 5
        rec2 = paper_trader.reconcile(conn, pid, brk)
        assert rec2['matched'] is False
        assert '005930' in rec2['qty_mismatch']


def test_positions_from_kis_balance_parsing():
    bal = {'output1': [
        {'pdno': '005930', 'hldg_qty': '28'},
        {'pdno': '000660', 'hldg_qty': '0'},      # 0주는 제외
    ]}
    assert paper_trader.positions_from_kis_balance(bal) == {'005930': 28}
