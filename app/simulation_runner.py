"""Walk-forward 시뮬레이션 — IS/OOS 분리 + Deflated Sharpe + gate 기록.

각 파라미터 조합을 IS 구간으로 백테스트(학습 관찰)하고 OOS 구간 성과를 보고하며,
n_trials(파라미터 공간 크기)로 다중검정을 보정한다.
docs/backtest-reliability/00-스펙-설계.md, 01-구현-플랜.md Task 9. Python 3.9 호환.
"""
from typing import Dict, List
import itertools
import uuid
import math

import backtester
import validation_harness as vh


def _n_obs(start: str, end: str) -> int:
    from datetime import date
    return max(int((date.fromisoformat(end) - date.fromisoformat(start)).days * 252 / 365), 5)


def _run_single(conn, batch_id: str, strategy: str, risk_profile: str,
                window_start: str, window_end: str, n_trials: int) -> None:
    (is_s, is_e), (oos_s, oos_e) = vh.split_is_oos(window_start, window_end)

    top_n = {'aggressive': 2, 'moderate': 3, 'defensive': 5}.get(risk_profile, 3)
    is_res = backtester.run_backtest(conn, strategy, is_s, is_e, top_n=top_n,
                                     fill_model='realistic')
    oos_res = backtester.run_backtest(conn, strategy, oos_s, oos_e, top_n=top_n,
                                      fill_model='realistic')

    dsr = vh.deflated_sharpe_ratio(
        oos_res['sharpe'], n_trials=n_trials, n_obs=_n_obs(oos_s, oos_e))
    passed, reason = vh.passes_gate(is_res, oos_res, dsr)

    conn.execute(
        """INSERT INTO simulation_runs
           (batch_id, strategy, risk_profile, cagr, mdd, sharpe, alpha, n_trades,
            is_cagr, oos_cagr, deflated_sharpe, cost_bps, gate_passed, gate_reason, status)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?, 'ok')""",
        (batch_id, strategy, risk_profile, oos_res['cagr'], oos_res['mdd'],
         oos_res['sharpe'], oos_res['alpha'], oos_res['n_trades'],
         is_res['cagr'], oos_res['cagr'], round(dsr, 4), 0.0,
         1 if passed else 0, reason))


def run_batch(conn, window_start: str, window_end: str, n: int = 10) -> Dict:
    """n회(파라미터 순환) walk-forward 시뮬레이션 실행 및 기록."""
    batch_id = str(uuid.uuid4())
    strategies = ['momentum', 'value', 'turnaround']
    risk_profiles = ['aggressive', 'moderate', 'defensive']
    params = list(itertools.product(strategies, risk_profiles))
    n_trials = len(params)
    param_list = [params[i % len(params)] for i in range(n)]

    results = {'completed': 0, 'failed': 0, 'gate_passed': 0}
    for strategy, risk in param_list:
        try:
            _run_single(conn, batch_id, strategy, risk,
                        window_start, window_end, n_trials)
            results['completed'] += 1
        except Exception:
            results['failed'] += 1
    row = conn.execute(
        "SELECT COUNT(*) AS c FROM simulation_runs WHERE batch_id=? AND gate_passed=1",
        (batch_id,)).fetchone()
    results['gate_passed'] = row['c']
    results['batch_id'] = batch_id
    return results
