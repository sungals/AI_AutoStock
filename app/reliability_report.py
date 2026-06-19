"""신뢰성 리포트 — 생존편향 경고 + OOS/Deflated Sharpe 노출.

일일 리포트/대시보드에 백테스트 신뢰성 지표를 표면화한다.
docs/backtest-reliability/00-스펙-설계.md §10, 01-구현-플랜.md Task 12. Python 3.9 호환.
"""
from typing import Dict, Optional

import bias_report


def estimate_universe_concentration(conn, start_date: str, end_date: str) -> Dict:
    """백테스트 유니버스의 종목 수·섹터 집중도를 측정한다."""
    rows = conn.execute(
        """SELECT DISTINCT p.stock_code, COALESCE(c.sector, 'UNKNOWN') AS sector
           FROM price_data p
           LEFT JOIN companies c ON c.stock_code = p.stock_code
           WHERE p.trade_date BETWEEN ? AND ?""",
        (start_date, end_date)).fetchall()
    universe_size = len(rows)
    sector_counts = {}  # type: Dict[str, int]
    for r in rows:
        sector = r['sector'] or 'UNKNOWN'
        sector_counts[sector] = sector_counts.get(sector, 0) + 1

    max_sector = None
    max_sector_weight = 0.0
    if universe_size:
        max_sector, max_count = max(sector_counts.items(), key=lambda x: x[1])
        max_sector_weight = float(max_count) / float(universe_size)

    warnings = []
    if universe_size and universe_size < 50:
        warnings.append(u'유니버스가 %d종목으로 작아 표본/집중 리스크가 큽니다.' % universe_size)
    if max_sector and max_sector != 'UNKNOWN' and max_sector_weight >= 0.50:
        warnings.append(u'%s 섹터 비중이 %.1f%%로 높아 섹터 집중 리스크가 큽니다.'
                        % (max_sector, max_sector_weight * 100.0))

    return {
        'universe_size': universe_size,
        'sector_counts': sector_counts,
        'max_sector': max_sector,
        'max_sector_weight': round(max_sector_weight, 4),
        'warning': u'⚠️ ' + ' '.join(warnings) if warnings else '',
    }


def build_report(conn, start_date: str, end_date: str,
                 batch_id: Optional[str] = None) -> Dict:
    """신뢰성 리포트 조립.

    Returns:
        {survivorship, concentration, runs_summary, best_gate_passed, text}
    """
    survivorship = bias_report.estimate_survivorship_bias(conn, start_date, end_date)
    concentration = estimate_universe_concentration(conn, start_date, end_date)

    where = "WHERE 1=1"
    args = []  # type: list
    if batch_id is not None:
        where += " AND batch_id = ?"
        args.append(batch_id)

    runs = conn.execute(
        "SELECT strategy, risk_profile, is_cagr, oos_cagr, deflated_sharpe, "
        "gate_passed, gate_reason FROM simulation_runs %s" % where, tuple(args)
    ).fetchall()

    total = len(runs)
    passed = [r for r in runs if r['gate_passed'] == 1]
    best = None
    if passed:
        best_row = max(passed, key=lambda r: (r['oos_cagr'] if r['oos_cagr'] is not None else -1e9))
        best = {
            'strategy': best_row['strategy'],
            'risk_profile': best_row['risk_profile'],
            'is_cagr': best_row['is_cagr'],
            'oos_cagr': best_row['oos_cagr'],
            'deflated_sharpe': best_row['deflated_sharpe'],
        }

    runs_summary = {
        'total': total,
        'gate_passed': len(passed),
        'gate_failed': total - len(passed),
    }

    # 사람이 읽는 텍스트
    lines = []
    if survivorship.get('warning'):
        lines.append(survivorship['warning'])
    if concentration.get('warning'):
        lines.append(concentration['warning'])
    lines.append(u'시뮬레이션 %d건 중 gate 통과 %d건 (과최적화 필터 적용).'
                 % (total, len(passed)))
    if best:
        lines.append(u'최우수(gate 통과): %s/%s — OOS CAGR %.2f%%, Deflated Sharpe %.3f'
                     % (best['strategy'], best['risk_profile'],
                        best['oos_cagr'] or 0.0, best['deflated_sharpe'] or 0.0))
    text = '\n'.join(lines)

    return {
        'survivorship': survivorship,
        'concentration': concentration,
        'runs_summary': runs_summary,
        'best_gate_passed': best,
        'text': text,
    }
