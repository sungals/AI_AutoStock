"""페이퍼 트레이딩 루프 — 시그널을 모의 브로커로 집행하고 체결을 기록한다.

안전 원칙(스캐폴딩 단계):
- **모의(mock) 포트폴리오 + 모의 브로커만** 허용. live/prod면 거부.
- 멱등성: 같은 날 같은 종목을 두 번 매수하지 않는다.
- 리스크 가드: 종목당 최대 비중(max_position_size), 현금 한도 내에서만.

아직 손절/청산/리밸런싱/실시간 체결추적은 포함하지 않는다(후속).
Python 3.9 호환.
"""
from typing import Dict, List, Optional, Sequence
from datetime import date

import db_portfolio


def run_paper_session(conn, portfolio_id: int, picks: Sequence[str],
                      broker=None, trade_date: Optional[str] = None,
                      reason: str = 'screening') -> Dict:
    """picks(매수 후보 종목코드)를 모의로 매수 집행하고 live_trades에 기록.

    Returns: {submitted, skipped, failed, orders:[...]}
    """
    pf = db_portfolio.get_live_portfolio(conn, portfolio_id)
    # ── 안전 가드 ──
    if pf['mode'] != 'mock':
        raise RuntimeError('페이퍼 트레이딩은 mock 포트폴리오에서만 가능합니다')
    if broker is None:
        import broker as broker_mod
        broker = broker_mod.get_broker()
    if not broker.is_mock():
        raise RuntimeError('페이퍼 트레이딩은 mock 브로커에서만 가능합니다')

    trade_date = trade_date or date.today().isoformat()
    holdings = db_portfolio.get_live_holdings(conn, portfolio_id)
    cash = float(pf['cash'])
    per_position_budget = float(pf['initial_capital']) * float(pf['max_position_size'])

    result = {'submitted': 0, 'skipped': 0, 'failed': 0, 'orders': []}  # type: Dict
    for code in picks:
        if code in holdings:                      # 이미 보유
            result['skipped'] += 1
            continue
        if db_portfolio.has_live_buy(conn, portfolio_id, code, trade_date):  # 멱등성
            result['skipped'] += 1
            continue

        price = broker.get_price(code)
        if not price or price <= 0:
            result['failed'] += 1
            continue

        budget = min(per_position_budget, cash)
        qty = int(budget // price)
        if qty <= 0:                              # 현금/한도 부족
            result['skipped'] += 1
            continue

        res = broker.place_order(code, 'buy', qty=qty, price=int(price))
        if not res.ok:
            result['failed'] += 1
            continue

        amount = qty * price
        db_portfolio.record_live_trade(
            conn, portfolio_id, code, trade_date, 'buy', qty, price,
            order_id=res.order_id, metadata={'reason': reason})
        db_portfolio.update_live_cash(conn, portfolio_id, -amount)
        cash -= amount
        result['submitted'] += 1
        result['orders'].append({'stock_code': code, 'qty': qty, 'price': int(price),
                                 'order_id': res.order_id})
    return result


def positions_from_kis_balance(balance: Dict) -> Dict[str, int]:
    """KIS 잔고 응답(output1)에서 {종목코드: 보유수량} 추출.

    MemoryBroker.get_balance()의 {'positions': {...}} 형태도 함께 지원.
    """
    if 'positions' in balance:                    # MemoryBroker
        return {k: int(v) for k, v in balance['positions'].items() if int(v) != 0}
    out = {}  # type: Dict[str, int]
    for row in balance.get('output1', []) or []:
        code = (row.get('pdno') or '').strip()
        qty = row.get('hldg_qty')
        try:
            q = int(qty)
        except (ValueError, TypeError):
            q = 0
        if code and q != 0:
            out[code] = q
    return out


def reconcile(conn, portfolio_id: int, broker) -> Dict:
    """DB 보유 vs 브로커 잔고 정합성 점검.

    Returns: {matched, db_only, broker_only, qty_mismatch}
    """
    db_h = db_portfolio.get_live_holdings(conn, portfolio_id)
    br_h = positions_from_kis_balance(broker.get_balance())

    db_only = sorted(set(db_h) - set(br_h))
    broker_only = sorted(set(br_h) - set(db_h))
    qty_mismatch = sorted(
        code for code in (set(db_h) & set(br_h)) if db_h[code] != br_h[code])
    matched = not db_only and not broker_only and not qty_mismatch
    return {'matched': matched, 'db_only': db_only,
            'broker_only': broker_only, 'qty_mismatch': qty_mismatch}
