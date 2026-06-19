"""포트폴리오 DB 헬퍼 — 가상/Mock 라이브 포트폴리오 최소 운영 기능."""
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
