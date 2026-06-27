"""모의/라이브 포트폴리오 성과 + 추적오차(tracking error) 기록.

매일 평가액·일일수익률·누적수익률과 벤치마크(기본 KOSPI=KS11)를 live_performance에
저장하고, 벤치마크 대비 추적오차/정보비율/액티브수익을 계산한다.
Python 3.9 호환.
"""
from typing import Callable, Dict, Optional
from datetime import date
import math

import db_portfolio


def _benchmark_close(conn, perf_date: str, symbol: str = 'KS11') -> Optional[float]:
    row = conn.execute(
        "SELECT close FROM macro_prices WHERE symbol=? AND trade_date<=? "
        "ORDER BY trade_date DESC LIMIT 1", (symbol, perf_date)).fetchone()
    return float(row['close']) if row and row['close'] else None


def portfolio_value(conn, portfolio_id: int, price_fn: Callable) -> float:
    pf = db_portfolio.get_live_portfolio(conn, portfolio_id)
    total = float(pf['cash'])
    for code, qty in db_portfolio.get_live_holdings(conn, portfolio_id).items():
        px = price_fn(code)
        if px:
            total += float(px) * qty
    return total


def snapshot(conn, portfolio_id: int, perf_date: str, price_fn: Callable,
             benchmark_symbol: str = 'KS11') -> Dict:
    """해당 일자의 평가액·수익률·벤치마크를 계산·저장(멱등).

    Returns: {portfolio_value, daily_return, cum_return, benchmark_daily_return,
              active_daily_return}
    """
    pf = db_portfolio.get_live_portfolio(conn, portfolio_id)
    initial = float(pf['initial_capital'])
    value = portfolio_value(conn, portfolio_id, price_fn)

    prev = conn.execute(
        """SELECT portfolio_value, benchmark_value FROM live_performance
           WHERE portfolio_id=? AND perf_date<? ORDER BY perf_date DESC LIMIT 1""",
        (portfolio_id, perf_date)).fetchone()

    bench = _benchmark_close(conn, perf_date, benchmark_symbol)

    daily_return = None
    bench_daily = None
    if prev and prev['portfolio_value']:
        daily_return = value / float(prev['portfolio_value']) - 1.0
        if bench is not None and prev['benchmark_value']:
            bench_daily = bench / float(prev['benchmark_value']) - 1.0
    cum_return = value / initial - 1.0 if initial > 0 else 0.0
    active_daily = (daily_return - bench_daily) \
        if (daily_return is not None and bench_daily is not None) else None

    conn.execute(
        """INSERT OR REPLACE INTO live_performance
           (portfolio_id, perf_date, portfolio_value, daily_return, cum_return,
            benchmark_value, benchmark_daily_return, active_daily_return)
           VALUES (?,?,?,?,?,?,?,?)""",
        (portfolio_id, perf_date, value,
         _r(daily_return), _r(cum_return), bench, _r(bench_daily), _r(active_daily)))
    return {'portfolio_value': value, 'daily_return': daily_return,
            'cum_return': cum_return, 'benchmark_daily_return': bench_daily,
            'active_daily_return': active_daily}


def tracking_error(conn, portfolio_id: int) -> Dict:
    """벤치마크 대비 추적오차(연율화) + 정보비율 + 일평균 액티브수익.

    추적오차 = std(액티브 일수익) × √252. 데이터 2일 미만이면 None.
    """
    rows = conn.execute(
        """SELECT active_daily_return FROM live_performance
           WHERE portfolio_id=? AND active_daily_return IS NOT NULL
           ORDER BY perf_date""", (portfolio_id,)).fetchall()
    active = [float(r['active_daily_return']) for r in rows]
    if len(active) < 2:
        return {'tracking_error': None, 'info_ratio': None,
                'active_return_mean_daily': None, 'n': len(active)}
    mean = sum(active) / len(active)
    var = sum((x - mean) ** 2 for x in active) / (len(active) - 1)   # 표본분산
    te = math.sqrt(var) * math.sqrt(252)
    info_ratio = (mean * 252) / te if te > 0 else 0.0
    return {'tracking_error': round(te, 4), 'info_ratio': round(info_ratio, 4),
            'active_return_mean_daily': round(mean, 6), 'n': len(active)}


def performance_summary(conn, portfolio_id: int) -> Dict:
    """누적 성과 요약: 포트폴리오/벤치마크 누적수익, 액티브, 추적오차, MDD."""
    rows = conn.execute(
        """SELECT perf_date, portfolio_value, cum_return, daily_return,
                  benchmark_daily_return FROM live_performance
           WHERE portfolio_id=? ORDER BY perf_date""", (portfolio_id,)).fetchall()
    if not rows:
        return {'days': 0}
    cum_return = rows[-1]['cum_return']

    # 벤치마크 누적(일수익 복리)
    bench_cum = 1.0
    for r in rows:
        if r['benchmark_daily_return'] is not None:
            bench_cum *= (1.0 + float(r['benchmark_daily_return']))
    bench_cum -= 1.0

    # MDD (포트폴리오 평가액 기준)
    peak = rows[0]['portfolio_value']
    mdd = 0.0
    for r in rows:
        v = r['portfolio_value']
        peak = max(peak, v)
        if peak > 0:
            mdd = max(mdd, (peak - v) / peak)

    te = tracking_error(conn, portfolio_id)
    return {
        'days': len(rows),
        'cum_return': round(cum_return, 4) if cum_return is not None else None,
        'benchmark_cum_return': round(bench_cum, 4),
        'active_return': round((cum_return or 0.0) - bench_cum, 4),
        'mdd': round(mdd, 4),
        'tracking_error': te['tracking_error'],
        'info_ratio': te['info_ratio'],
    }


def _r(x: Optional[float]) -> Optional[float]:
    return round(x, 6) if x is not None else None
