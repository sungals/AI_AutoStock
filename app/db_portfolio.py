"""포트폴리오 DB 헬퍼 — 가상/Mock 라이브 포트폴리오 최소 운영 기능."""
import json
from typing import Dict, Optional


def create_virtual_portfolio(conn, name: str, strategy: str,
                             initial_capital: float = 10_000_000.0,
                             user_id: Optional[int] = None,
                             risk_profile: Optional[str] = None,
                             portfolio_type: str = 'manual',
                             horizon: Optional[str] = None) -> int:
    conn.execute(
        """INSERT INTO virtual_portfolios
           (user_id, name, strategy, risk_profile, portfolio_type, horizon,
            initial_capital, cash)
           VALUES (?,?,?,?,?,?,?,?)""",
        (user_id, name, strategy, risk_profile, portfolio_type, horizon,
         initial_capital, initial_capital))
    return int(conn.execute("SELECT last_insert_rowid() AS id").fetchone()['id'])


def record_virtual_trade(conn, portfolio_id: int, stock_code: str, trade_date: str,
                         trade_type: str, quantity: int, price: float,
                         reason: str = '', exit_reason: Optional[str] = None) -> int:
    if trade_type not in ('buy', 'sell'):
        raise ValueError('trade_type must be buy or sell')
    if quantity <= 0 or price <= 0:
        raise ValueError('quantity and price must be positive')
    amount = float(quantity) * float(price)
    cash_delta = -amount if trade_type == 'buy' else amount
    row = conn.execute(
        "SELECT cash FROM virtual_portfolios WHERE id=?", (portfolio_id,)).fetchone()
    if not row:
        raise ValueError('portfolio not found')
    if trade_type == 'buy' and row['cash'] < amount:
        raise ValueError('insufficient cash')
    conn.execute(
        """INSERT INTO virtual_trades
           (portfolio_id, stock_code, trade_date, trade_type, quantity, price,
            amount, reason, exit_reason)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (portfolio_id, stock_code, trade_date, trade_type, quantity, price,
         amount, reason, exit_reason))
    conn.execute(
        "UPDATE virtual_portfolios SET cash=cash+?, updated_at=datetime('now') WHERE id=?",
        (cash_delta, portfolio_id))
    return int(conn.execute("SELECT last_insert_rowid() AS id").fetchone()['id'])


def get_virtual_holdings(conn, portfolio_id: int) -> Dict[str, int]:
    rows = conn.execute(
        """SELECT stock_code,
                  SUM(CASE WHEN trade_type='buy' THEN quantity ELSE -quantity END) AS qty
           FROM virtual_trades
           WHERE portfolio_id=?
           GROUP BY stock_code""",
        (portfolio_id,)).fetchall()
    return {r['stock_code']: int(r['qty']) for r in rows if r['qty'] and int(r['qty']) != 0}


def _close_on_or_before(conn, stock_code: str, as_of: str) -> Optional[float]:
    row = conn.execute(
        """SELECT close FROM price_data
           WHERE stock_code=? AND trade_date<=?
           ORDER BY trade_date DESC LIMIT 1""",
        (stock_code, as_of)).fetchone()
    return float(row['close']) if row and row['close'] is not None else None


def calculate_virtual_value(conn, portfolio_id: int, as_of: str) -> float:
    row = conn.execute(
        "SELECT cash FROM virtual_portfolios WHERE id=?", (portfolio_id,)).fetchone()
    if not row:
        raise ValueError('portfolio not found')
    value = float(row['cash'])
    for code, qty in get_virtual_holdings(conn, portfolio_id).items():
        px = _close_on_or_before(conn, code, as_of)
        if px is not None:
            value += qty * px
    return round(value, 4)


def save_virtual_performance(conn, portfolio_id: int, perf_date: str,
                             portfolio_value: float) -> None:
    row = conn.execute(
        "SELECT initial_capital FROM virtual_portfolios WHERE id=?",
        (portfolio_id,)).fetchone()
    if not row:
        raise ValueError('portfolio not found')
    initial = float(row['initial_capital'])
    total_return = ((portfolio_value - initial) / initial * 100.0) if initial > 0 else 0.0
    prev = conn.execute(
        """SELECT portfolio_value FROM virtual_performance
           WHERE portfolio_id=? AND perf_date<?
           ORDER BY perf_date DESC LIMIT 1""",
        (portfolio_id, perf_date)).fetchone()
    daily_return = None
    if prev and prev['portfolio_value']:
        daily_return = (portfolio_value - prev['portfolio_value']) / prev['portfolio_value'] * 100.0
    conn.execute(
        """INSERT OR REPLACE INTO virtual_performance
           (portfolio_id, perf_date, portfolio_value, daily_return, total_return)
           VALUES (?,?,?,?,?)""",
        (portfolio_id, perf_date, portfolio_value, daily_return, round(total_return, 4)))


def create_live_portfolio(conn, name: str, initial_capital: float,
                          mode: str = 'mock', user_id: Optional[int] = None,
                          strategy: Optional[str] = None,
                          max_invest_ratio: float = 0.9,
                          daily_loss_limit: float = 0.03,
                          max_position_size: float = 0.2,
                          sizing_mode: str = 'equal') -> int:
    if mode not in ('mock', 'live'):
        raise ValueError('mode must be mock or live')
    conn.execute(
        """INSERT INTO live_portfolios
           (user_id, name, mode, initial_capital, cash, strategy,
            max_invest_ratio, daily_loss_limit, max_position_size, sizing_mode)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (user_id, name, mode, initial_capital, initial_capital, strategy,
         max_invest_ratio, daily_loss_limit, max_position_size, sizing_mode))
    return int(conn.execute("SELECT last_insert_rowid() AS id").fetchone()['id'])


def get_live_portfolio(conn, portfolio_id: int):
    row = conn.execute(
        "SELECT * FROM live_portfolios WHERE id=?", (portfolio_id,)).fetchone()
    if not row:
        raise ValueError('portfolio not found')
    return row


def record_live_trade(conn, portfolio_id: int, stock_code: str, trade_date: str,
                      trade_type: str, quantity: int, price: float,
                      order_id: Optional[str] = None,
                      exit_reason: Optional[str] = None,
                      metadata: Optional[Dict] = None) -> int:
    """라이브/모의 체결 기록. trade_type: 'buy'|'sell'."""
    amount = quantity * price
    conn.execute(
        """INSERT INTO live_trades
           (portfolio_id, stock_code, trade_date, trade_type, quantity, price,
            amount, exit_reason, order_id, metadata)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (portfolio_id, stock_code, trade_date, trade_type, quantity, price,
         amount, exit_reason, order_id, json.dumps(metadata or {}, ensure_ascii=False)))
    return int(conn.execute("SELECT last_insert_rowid() AS id").fetchone()['id'])


def get_live_holdings(conn, portfolio_id: int) -> Dict[str, int]:
    """live_trades 누적(매수-매도)으로 보유 수량 산출. 0주는 제외."""
    rows = conn.execute(
        """SELECT stock_code, trade_type, SUM(quantity) AS q
           FROM live_trades WHERE portfolio_id=? GROUP BY stock_code, trade_type""",
        (portfolio_id,)).fetchall()
    holdings = {}  # type: Dict[str, int]
    for r in rows:
        sign = 1 if r['trade_type'] == 'buy' else -1
        holdings[r['stock_code']] = holdings.get(r['stock_code'], 0) + sign * int(r['q'])
    return {k: v for k, v in holdings.items() if v != 0}


def update_live_cash(conn, portfolio_id: int, delta: float) -> None:
    """현금 증감(매수 -, 매도 +)."""
    conn.execute(
        "UPDATE live_portfolios SET cash = cash + ? WHERE id=?",
        (delta, portfolio_id))


def has_live_buy(conn, portfolio_id: int, stock_code: str, trade_date: str) -> bool:
    """멱등성: 해당 종목을 그날 이미 매수 기록했는지."""
    row = conn.execute(
        """SELECT 1 FROM live_trades
           WHERE portfolio_id=? AND stock_code=? AND trade_date=? AND trade_type='buy'
           LIMIT 1""",
        (portfolio_id, stock_code, trade_date)).fetchone()
    return row is not None
