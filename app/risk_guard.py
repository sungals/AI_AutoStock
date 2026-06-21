"""리스크 가드 — 킬스위치 + 일일 손실한도 집행.

매매 직전 `pre_trade_check()`로 진입 허용 여부를 결정한다. 차단 사유:
1) 전역 킬스위치(config.TRADING_KILL_SWITCH) 또는 portfolio_id=0 전역 halt
2) 해당 포트폴리오 halt(이전에 트립됨)
3) 일일 손실이 daily_loss_limit 이상 → 킬스위치 자동 트립 후 차단

일일 기준값(start_value)은 그날 첫 점검 시점의 평가액으로 저장한다.
Python 3.9 호환.
"""
from typing import Callable, Dict, Optional, Tuple
from datetime import date

import config
import db_portfolio

_GLOBAL = 0   # 전역 킬스위치용 portfolio_id


# ── 킬스위치 상태 ──

def is_halted(conn, portfolio_id: int) -> Tuple[bool, str]:
    """포트폴리오(또는 전역) 매매 중단 여부."""
    if config.TRADING_KILL_SWITCH:
        return True, '전역 킬스위치(config)'
    for pid in (_GLOBAL, portfolio_id):
        row = conn.execute(
            "SELECT halted, reason FROM risk_state WHERE portfolio_id=?",
            (pid,)).fetchone()
        if row and row['halted']:
            scope = '전역' if pid == _GLOBAL else '포트폴리오'
            return True, '%s 킬스위치: %s' % (scope, row['reason'] or '')
    return False, ''


def trip_kill_switch(conn, portfolio_id: int, reason: str) -> None:
    """매매 중단(트립). portfolio_id=0 이면 전역."""
    conn.execute(
        """INSERT INTO risk_state (portfolio_id, halted, reason, halted_at)
           VALUES (?, 1, ?, datetime('now'))
           ON CONFLICT(portfolio_id) DO UPDATE SET
             halted=1, reason=excluded.reason, halted_at=datetime('now')""",
        (portfolio_id, reason))


def reset_kill_switch(conn, portfolio_id: int) -> None:
    """매매 재개(수동 해제)."""
    conn.execute(
        """INSERT INTO risk_state (portfolio_id, halted, reason, halted_at)
           VALUES (?, 0, NULL, NULL)
           ON CONFLICT(portfolio_id) DO UPDATE SET halted=0, reason=NULL""",
        (portfolio_id,))


# ── 평가액 / 일일 손실 ──

def portfolio_value(conn, portfolio_id: int, price_fn: Callable) -> float:
    """현금 + 보유평가액(현재가 price_fn으로 평가)."""
    pf = db_portfolio.get_live_portfolio(conn, portfolio_id)
    total = float(pf['cash'])
    for code, qty in db_portfolio.get_live_holdings(conn, portfolio_id).items():
        px = price_fn(code)
        if px:
            total += float(px) * qty
    return total


def _day_start_value(conn, portfolio_id: int, trade_date: str,
                     current_value: float) -> float:
    """그날 기준 평가액. 없으면 현재값으로 최초 1회 저장."""
    row = conn.execute(
        "SELECT start_value FROM risk_daily WHERE portfolio_id=? AND trade_date=?",
        (portfolio_id, trade_date)).fetchone()
    if row:
        return float(row['start_value'])
    conn.execute(
        "INSERT INTO risk_daily (portfolio_id, trade_date, start_value) VALUES (?,?,?)",
        (portfolio_id, trade_date, current_value))
    return current_value


def check_daily_loss(conn, portfolio_id: int, price_fn: Callable,
                     trade_date: Optional[str] = None) -> Dict:
    """일일 손실률 계산. 한도 초과면 킬스위치 트립.

    Returns: {loss_pct, limit, exceeded}
    """
    trade_date = trade_date or date.today().isoformat()
    pf = db_portfolio.get_live_portfolio(conn, portfolio_id)
    limit = float(pf['daily_loss_limit'])
    cur = portfolio_value(conn, portfolio_id, price_fn)
    start = _day_start_value(conn, portfolio_id, trade_date, cur)
    loss_pct = (start - cur) / start if start > 0 else 0.0
    exceeded = loss_pct >= limit
    if exceeded:
        trip_kill_switch(
            conn, portfolio_id,
            '일일 손실한도 초과 %.2f%% ≥ %.2f%%' % (loss_pct * 100, limit * 100))
    return {'loss_pct': round(loss_pct, 4), 'limit': limit, 'exceeded': exceeded}


# ── 통합 게이트 ──

def pre_trade_check(conn, portfolio_id: int, price_fn: Callable,
                    trade_date: Optional[str] = None) -> Dict:
    """매매 직전 종합 점검. Returns: {allowed, reason, daily_loss_pct}."""
    halted, reason = is_halted(conn, portfolio_id)
    if halted:
        return {'allowed': False, 'reason': reason, 'daily_loss_pct': None}

    dl = check_daily_loss(conn, portfolio_id, price_fn, trade_date)
    if dl['exceeded']:
        return {'allowed': False,
                'reason': '일일 손실한도 초과 (%.2f%% ≥ %.2f%%)'
                          % (dl['loss_pct'] * 100, dl['limit'] * 100),
                'daily_loss_pct': dl['loss_pct']}
    return {'allowed': True, 'reason': '', 'daily_loss_pct': dl['loss_pct']}
