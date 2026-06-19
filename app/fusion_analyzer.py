"""융합 분석 — 기술 점수 + 경험 점수 앙상블.

05-구현-가이드 Phase 7. 계산은 순수 함수로 분리하고, 저장은 connection injection으로 처리한다.
Python 3.9 호환.
"""
from typing import Dict


def calculate_fusion_signal(tech_score: float, emp_score: float,
                            tech_weight: float = 0.5,
                            emp_weight: float = 0.5,
                            amplifier: float = 1.2,
                            dampener: float = 0.7) -> Dict:
    """기술적 점수와 경험적 점수를 융합해 추천을 산출한다."""
    fusion_score = tech_score * tech_weight + emp_score * emp_weight
    agreement = ((tech_score > 0 and emp_score > 0) or
                 (tech_score < 0 and emp_score < 0))
    if agreement:
        fusion_score *= amplifier
        confidence = 0.8
    else:
        fusion_score *= dampener
        confidence = 0.4

    if fusion_score >= 60:
        recommendation = 'STRONG_BUY'
    elif fusion_score >= 30:
        recommendation = 'BUY'
    elif fusion_score <= -60:
        recommendation = 'STRONG_SELL'
    elif fusion_score <= -30:
        recommendation = 'SELL'
    else:
        recommendation = 'HOLD'

    return {
        'fusion_score': round(fusion_score, 2),
        'confidence': confidence,
        'agreement': 1 if agreement else 0,
        'recommendation': recommendation,
    }


def save_fusion_signal(conn, stock_code: str, calc_date: str,
                       tech_score: float, emp_score: float,
                       signal: Dict, regime: str = 'sideways') -> None:
    """fusion_signals에 멱등 저장."""
    conn.execute(
        """INSERT OR REPLACE INTO fusion_signals
           (stock_code, calc_date, tech_score, emp_score, fusion_score,
            confidence, agreement, recommendation, regime)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (stock_code, calc_date, tech_score, emp_score,
         signal['fusion_score'], signal['confidence'], signal['agreement'],
         signal['recommendation'], regime))


def _latest_screening_score(conn, stock_code: str, calc_date: str) -> float:
    row = conn.execute(
        """SELECT MAX(score) AS s FROM screening_results
           WHERE stock_code=? AND screen_date=?""",
        (stock_code, calc_date)).fetchone()
    return float(row['s']) if row and row['s'] is not None else 0.0


def _sentiment_emp_score(conn, stock_code: str, calc_date: str) -> float:
    row = conn.execute(
        """SELECT composite_score FROM sentiment_scores
           WHERE stock_code=? AND score_date=?""",
        (stock_code, calc_date)).fetchone()
    if not row or row['composite_score'] is None:
        return 0.0
    return max(-100.0, min(100.0, float(row['composite_score']) * 100.0))


def calculate_all(conn, calc_date: str, regime: str = 'sideways') -> Dict[str, Dict]:
    """현재 구현된 데이터로 전체 종목 융합 시그널을 계산한다.

    tech_score는 해당일 스크리닝 최고점, emp_score는 감성 composite_score를 -100~100으로 환산한다.
    """
    rows = conn.execute("SELECT stock_code FROM companies ORDER BY stock_code").fetchall()
    out = {}
    for r in rows:
        code = r['stock_code']
        tech_score = _latest_screening_score(conn, code, calc_date)
        emp_score = _sentiment_emp_score(conn, code, calc_date)
        signal = calculate_fusion_signal(tech_score, emp_score)
        save_fusion_signal(conn, code, calc_date, tech_score, emp_score, signal, regime=regime)
        out[code] = signal
    return out
