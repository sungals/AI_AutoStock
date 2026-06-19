"""알고리즘 파라미터 최적화 — gate 통과 run만 반영.

과최적화 차단: simulation_runs에서 gate_passed=1 인 run만 후보로 사용한다.
탈락 파라미터는 반영하지 않고 사유를 로깅한다.
docs/backtest-reliability/00-스펙-설계.md, 01-구현-플랜.md Task 10. Python 3.9 호환.
"""
from typing import Dict, Optional
import logging

logger = logging.getLogger(__name__)


def apply_optimal_params(conn, batch_id: Optional[str] = None) -> Dict:
    """gate 통과 run 중 OOS CAGR 최고 전략의 파라미터를 algo_params에 반영.

    Returns:
        {applied, skipped, best_strategy, best_oos_cagr}
    """
    where = "WHERE 1=1"
    args = []  # type: list
    if batch_id is not None:
        where += " AND batch_id = ?"
        args.append(batch_id)

    all_runs = conn.execute(
        "SELECT strategy, oos_cagr, deflated_sharpe, gate_passed, gate_reason "
        "FROM simulation_runs %s" % where, tuple(args)).fetchall()

    passed = [r for r in all_runs if r['gate_passed'] == 1]
    skipped = [r for r in all_runs if r['gate_passed'] != 1]

    for r in skipped:
        logger.info("param skipped: strategy=%s reason=%s",
                    r['strategy'], r['gate_reason'])

    if not passed:
        return {'applied': False, 'skipped': len(skipped),
                'best_strategy': None, 'best_oos_cagr': None}

    best = max(passed, key=lambda r: (r['oos_cagr'] if r['oos_cagr'] is not None else -1e9))
    conn.execute(
        "INSERT INTO algo_params (param_name, param_value, source) VALUES (?,?, 'optimizer')",
        ('best_strategy_%s' % best['strategy'], float(best['oos_cagr'] or 0.0)))

    return {'applied': True, 'skipped': len(skipped),
            'best_strategy': best['strategy'], 'best_oos_cagr': best['oos_cagr']}
