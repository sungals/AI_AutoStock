"""청산(매도) 로직 — 트레일링 스탑 / 하드 손절 / 보유기간 초과.

보유 포지션을 점검해 청산 규칙에 걸리면 모의 브로커로 전량 매도하고 live_trades에 기록한다.
청산(리스크 축소)은 **킬스위치와 무관하게 항상 허용**한다(손절을 막으면 안 됨).

규칙 우선순위: 하드 손절 → 트레일링 스탑 → 보유기간 초과.
Python 3.9 호환.
"""
from typing import Dict, Optional
from datetime import date

import config
import db_portfolio
import portfolio_operations as ops


def _highest_since(conn, stock_code: str, entry_date: str, as_of: str,
                   fallback: float) -> float:
    """진입 후 최고가(price_data의 high/close). 없으면 fallback."""
    try:
        row = conn.execute(
            """SELECT MAX(high) AS h, MAX(close) AS c FROM price_data
               WHERE stock_code=? AND trade_date BETWEEN ? AND ?""",
            (stock_code, entry_date, as_of)).fetchone()
    except Exception:
        row = None
    high = None
    if row:
        high = row['h'] if row['h'] is not None else row['c']
    return max(float(high), fallback) if high else fallback


def run_exits(conn, portfolio_id: int, broker, trade_date: Optional[str] = None,
              trail_pct: Optional[float] = None,
              stop_loss_pct: Optional[float] = None,
              max_hold_days: Optional[int] = None) -> Dict:
    """보유 포지션 청산 점검·실행.

    Returns: {sold, held, failed, exits:[{stock_code, qty, price, reason, pnl_pct}]}
    """
    pf = db_portfolio.get_live_portfolio(conn, portfolio_id)
    if pf['mode'] != 'mock':
        raise RuntimeError('청산도 mock 포트폴리오에서만 (스캐폴딩 단계)')
    if not broker.is_mock():
        raise RuntimeError('청산도 mock 브로커에서만 (스캐폴딩 단계)')

    trail_pct = config.EXIT_TRAIL_PCT if trail_pct is None else trail_pct
    stop_loss_pct = config.EXIT_STOP_LOSS_PCT if stop_loss_pct is None else stop_loss_pct
    max_hold_days = config.EXIT_MAX_HOLD_DAYS if max_hold_days is None else max_hold_days
    trade_date = trade_date or date.today().isoformat()

    result = {'sold': 0, 'held': 0, 'failed': 0, 'exits': []}  # type: Dict
    for code, pos in db_portfolio.get_live_positions(conn, portfolio_id).items():
        cur = broker.get_price(code)
        if not cur or cur <= 0:
            result['held'] += 1
            continue
        entry = pos['avg_price']
        high = _highest_since(conn, code, pos['entry_date'], trade_date, max(entry, cur))

        if ops.check_stop_loss(entry, cur, stop_loss_pct):
            reason = 'stop_loss'
        elif ops.check_trailing_stop(entry, high, cur, trail_pct):
            reason = 'trailing_stop'
        elif ops.check_timeout_exit(pos['entry_date'], trade_date, max_hold_days):
            reason = 'timeout'
        else:
            result['held'] += 1
            continue

        res = broker.place_order(code, 'sell', qty=pos['qty'], price=int(cur))
        if not res.ok:
            result['failed'] += 1
            continue

        db_portfolio.record_live_trade(
            conn, portfolio_id, code, trade_date, 'sell', pos['qty'], cur,
            order_id=res.order_id, exit_reason=reason, metadata={'reason': reason})
        db_portfolio.update_live_cash(conn, portfolio_id, pos['qty'] * cur)
        pnl_pct = round((cur - entry) / entry * 100, 2) if entry else 0.0
        result['sold'] += 1
        result['exits'].append({'stock_code': code, 'qty': pos['qty'],
                                'price': int(cur), 'reason': reason, 'pnl_pct': pnl_pct})
    return result
