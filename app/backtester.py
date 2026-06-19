"""백테스터 — price_data 기반 모멘텀 백테스트 + 신뢰성 레이어 통합.

- 재무 조회는 point_in_time(PIT 게이트)을 경유 (미래참조 차단).
- 체결은 execution_model(비용·체결가능성)을 경유 (fill_model='realistic').
- fill_model='ideal'은 비용 0 (비교용 기준선).
docs/backtest-reliability/00-스펙-설계.md §4, 01-구현-플랜.md Task 6. Python 3.9 호환.
"""
from typing import Dict, List, Optional
import math

import config
import point_in_time
import execution_model as em


def _all_trade_dates(conn, start_date: str, end_date: str) -> List[str]:
    rows = conn.execute(
        """SELECT DISTINCT trade_date FROM price_data
           WHERE trade_date BETWEEN ? AND ? ORDER BY trade_date""",
        (start_date, end_date)).fetchall()
    return [r['trade_date'] for r in rows]


def _close_on_or_before(conn, stock_code: str, as_of: str) -> Optional[int]:
    row = conn.execute(
        """SELECT close FROM price_data
           WHERE stock_code = ? AND trade_date <= ?
           ORDER BY trade_date DESC LIMIT 1""", (stock_code, as_of)).fetchone()
    return int(row['close']) if row and row['close'] else None


def _ohlcv_on(conn, stock_code: str, trade_date: str) -> Optional[Dict]:
    row = conn.execute(
        "SELECT * FROM price_data WHERE stock_code = ? AND trade_date = ?",
        (stock_code, trade_date)).fetchone()
    return dict(row) if row else None


def _trailing_return(conn, stock_code: str, as_of: str, lookback_date: str) -> Optional[float]:
    now = _close_on_or_before(conn, stock_code, as_of)
    past = _close_on_or_before(conn, stock_code, lookback_date)
    if not now or not past or past <= 0:
        return None
    return (now - past) / past


def _pick_momentum(conn, as_of: str, lookback_date: str, top_n: int,
                   fill_model: str) -> List[str]:
    """as_of 시점 모멘텀 상위 top_n 종목 선택 (미래참조 없음)."""
    companies = conn.execute(
        "SELECT corp_code, stock_code FROM companies").fetchall()
    scored = []
    for c in companies:
        code = c['stock_code']
        ret = _trailing_return(conn, code, as_of, lookback_date)
        if ret is None:
            continue
        # PIT 게이트 경유 — 펀더멘털 건전성 필터 (재무 없으면 통과)
        metrics = point_in_time.get_metrics_asof(
            conn, c['corp_code'], as_of, stock_code=code)
        if metrics.get('debt_ratio') is not None and metrics['debt_ratio'] > 1000:
            continue   # 극단적 고부채 제외
        # 체결 가능성 (realistic에서만 엄격 적용)
        if fill_model == 'realistic':
            ohlcv = _ohlcv_on(conn, code, as_of)
            if ohlcv and not em.is_tradable('buy', ohlcv, prev_close=ohlcv['close']):
                continue
        scored.append((ret, code))
    scored.sort(reverse=True)
    return [code for _, code in scored[:top_n]]


def _score_value(m: Dict) -> Optional[float]:
    """가치주 점수 (05-구현-가이드 §4.2). per/pbr/roe 필수, 40점 이상만."""
    if m.get('per') is None or m.get('pbr') is None or m.get('roe') is None:
        return None
    s = 0.0
    if 0 < m['per'] < 10:
        s += 25
    if 0 < m['pbr'] < 1.5:
        s += 20
    if m['roe'] > 10:
        s += 25
    if m.get('debt_ratio') is not None and m['debt_ratio'] < 100:
        s += 20
    return s if s >= 40 else None


def _score_turnaround(m: Dict) -> Optional[float]:
    """실적 전환주 점수. 흑자전환·매출급증·ROE·저부채. 30점 이상만."""
    s = 0.0
    if m.get('opincome_turnaround') == 1:
        s += 30
    if m.get('revenue_growth_yoy') is not None and m['revenue_growth_yoy'] > 20:
        s += 25
    if m.get('roe') is not None and m['roe'] > 5:
        s += 20
    if m.get('debt_ratio') is not None and m['debt_ratio'] < 150:
        s += 15
    return s if s >= 30 else None


def _pick_fundamental(conn, as_of: str, top_n: int, fill_model: str,
                      scorer) -> List[str]:
    """PIT 지표 기반 펀더멘털 전략 종목 선택 (value/turnaround 공용)."""
    companies = conn.execute(
        "SELECT corp_code, stock_code FROM companies").fetchall()
    scored = []
    for c in companies:
        code = c['stock_code']
        metrics = point_in_time.get_metrics_asof(
            conn, c['corp_code'], as_of, stock_code=code)
        sc = scorer(metrics)
        if sc is None:
            continue
        if fill_model == 'realistic':
            ohlcv = _ohlcv_on(conn, code, as_of)
            if ohlcv and not em.is_tradable('buy', ohlcv, prev_close=ohlcv['close']):
                continue
        scored.append((sc, code))
    scored.sort(key=lambda x: (-x[0], x[1]))   # 점수 내림차순, 동점은 코드순(결정적)
    return [code for _, code in scored[:top_n]]


def _select(conn, strategy: str, as_of: str, lookback_date: str,
            top_n: int, fill_model: str) -> List[str]:
    """전략별 종목 선택 디스패처."""
    if strategy == 'momentum':
        return _pick_momentum(conn, as_of, lookback_date, top_n, fill_model)
    if strategy == 'value':
        return _pick_fundamental(conn, as_of, top_n, fill_model, _score_value)
    if strategy == 'turnaround':
        return _pick_fundamental(conn, as_of, top_n, fill_model, _score_turnaround)
    raise ValueError('unknown strategy: %s' % strategy)


def _benchmark_cagr(conn, start_date: str, end_date: str, n_days: int) -> float:
    """벤치마크 = 유니버스 동일가중 buy&hold CAGR (시장 프록시)."""
    companies = conn.execute("SELECT stock_code FROM companies").fetchall()
    rets = []
    for c in companies:
        s = _close_on_or_before(conn, c['stock_code'], start_date)
        e = _close_on_or_before(conn, c['stock_code'], end_date)
        if s and e and s > 0:
            rets.append(e / s)
    if not rets:
        return 0.0
    avg_mult = sum(rets) / len(rets)        # 동일가중 총수익 배수
    years = max(n_days / 252.0, 1e-9)
    if avg_mult <= 0:
        return 0.0
    return (avg_mult ** (1.0 / years) - 1.0) * 100.0


def run_backtest(conn, strategy: str, start_date: str, end_date: str,
                 top_n: int = 3, fill_model: str = 'realistic',
                 commission_rate: Optional[float] = None,
                 slippage_bps: Optional[float] = None,
                 initial_capital: float = 10_000_000.0,
                 rebalance_days: int = 20, lookback: int = 20) -> Dict:
    """모멘텀 백테스트 실행.

    Returns:
        {cagr, mdd, sharpe, alpha, n_trades, final_value, fill_model}
    """
    if commission_rate is None:
        commission_rate = config.COMMISSION_RATE
    if slippage_bps is None:
        slippage_bps = config.SLIPPAGE_BPS
    if fill_model == 'ideal':
        commission_rate, slippage_bps = 0.0, 0.0

    dates = _all_trade_dates(conn, start_date, end_date)
    if len(dates) < lookback + 2:
        return {'cagr': 0.0, 'mdd': 0.0, 'sharpe': 0.0, 'alpha': 0.0,
                'n_trades': 0, 'final_value': initial_capital, 'fill_model': fill_model}

    cash = initial_capital
    holdings = {}  # type: Dict[str, int]
    n_trades = 0
    values = []  # 일별 포트폴리오 가치

    def sell_all(t):
        nonlocal cash, n_trades
        for code, qty in list(holdings.items()):
            px = _close_on_or_before(conn, code, t)
            if px is None:
                continue
            r = em.apply_costs('sell', px, qty, t, commission_rate, slippage_bps)
            cash += r['net']
            n_trades += 1
        holdings.clear()

    for i, t in enumerate(dates):
        # 리밸런싱 시점 (lookback 이후, rebalance_days 간격)
        if i >= lookback and (i - lookback) % rebalance_days == 0:
            sell_all(t)
            lookback_date = dates[i - lookback]
            picks = _select(conn, strategy, t, lookback_date, top_n, fill_model)
            if picks:
                budget = cash / len(picks)
                for code in picks:
                    px = _close_on_or_before(conn, code, t)
                    if not px:
                        continue
                    qty = int(budget // px)
                    if qty <= 0:
                        continue
                    r = em.apply_costs('buy', px, qty, t, commission_rate, slippage_bps)
                    if r['net'] <= cash:
                        cash -= r['net']
                        holdings[code] = holdings.get(code, 0) + qty
                        n_trades += 1

        # 일별 평가
        mkt = 0.0
        for code, qty in holdings.items():
            px = _close_on_or_before(conn, code, t)
            if px:
                mkt += px * qty
        values.append(cash + mkt)

    final_value = values[-1]
    years = max(len(dates) / 252.0, 1e-9)
    cagr = ((final_value / initial_capital) ** (1.0 / years) - 1.0) * 100.0 \
        if initial_capital > 0 and final_value > 0 else 0.0

    # MDD
    peak, mdd = values[0], 0.0
    for v in values:
        peak = max(peak, v)
        if peak > 0:
            mdd = max(mdd, (peak - v) / peak)
    mdd *= 100.0

    # Sharpe (일별 수익률 연율화)
    daily = []
    for j in range(1, len(values)):
        if values[j - 1] > 0:
            daily.append(values[j] / values[j - 1] - 1.0)
    if len(daily) >= 5:
        mean = sum(daily) / len(daily)
        var = sum((x - mean) ** 2 for x in daily) / len(daily)
        std = math.sqrt(var)
        rf = 0.035 / 252.0
        sharpe = (mean - rf) / std * math.sqrt(252) if std > 0 else 0.0
    else:
        sharpe = 0.0

    # Alpha = 전략 CAGR − 벤치마크(유니버스 동일가중 buy&hold) CAGR
    benchmark = _benchmark_cagr(conn, dates[0], dates[-1], len(dates))
    alpha = round(cagr - benchmark, 4)

    return {'cagr': round(cagr, 4), 'mdd': round(mdd, 4), 'sharpe': round(sharpe, 4),
            'alpha': alpha, 'benchmark_cagr': round(benchmark, 4),
            'n_trades': n_trades, 'final_value': final_value,
            'fill_model': fill_model}
