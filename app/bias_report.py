"""생존편향(Survivorship Bias) 정량화·경고.

현재 데이터로는 상장폐지 종목의 과거 시세가 없어 생존편향을 완전 제거할 수 없다.
따라서 그 크기를 추정·경고하고, 보고 수익률에 보수적 haircut을 적용한다.
이 모듈은 수익률을 '낮추는' 방향으로만 작동한다.
docs/backtest-reliability/00-스펙-설계.md §4.4. Python 3.9 호환.
"""
from typing import Dict


# 소멸 비율 1.0당 차감할 CAGR 포인트 (보수적 휴리스틱; config로 분리 가능)
_HAIRCUT_PER_DELISTED_RATIO = 10.0


def estimate_survivorship_bias(conn, start_date: str, end_date: str) -> Dict:
    """유니버스 변화로 생존편향 규모를 추정.

    구간 내 등장한 종목 중, 마지막 거래일이 end_date보다 이른(중도 소멸 추정) 비율을 계산.

    Returns:
        {'delisted_ratio', 'estimated_cagr_haircut_pct', 'warning'}
    """
    rows = conn.execute(
        """
        SELECT stock_code, MAX(trade_date) AS last_date
        FROM price_data
        WHERE trade_date BETWEEN ? AND ?
        GROUP BY stock_code
        """,
        (start_date, end_date),
    ).fetchall()

    total = len(rows)
    if total == 0:
        return {'delisted_ratio': 0.0, 'estimated_cagr_haircut_pct': 0.0,
                'warning': ''}

    delisted = sum(1 for r in rows if r['last_date'] < end_date)
    ratio = delisted / total
    haircut = round(ratio * _HAIRCUT_PER_DELISTED_RATIO, 2)

    warning = ''
    if delisted > 0:
        warning = (u'⚠️ 상장폐지/중도소멸 추정 종목 %d/%d (%.0f%%) 미반영 — '
                   u'실제 수익률은 보고치보다 낮을 수 있음.'
                   % (delisted, total, ratio * 100))

    return {
        'delisted_ratio': ratio,
        'estimated_cagr_haircut_pct': haircut,
        'warning': warning,
    }


def apply_haircut(reported_cagr: float, haircut_pct: float) -> float:
    """보고 CAGR에 보수적 haircut 적용 (낮추는 방향)."""
    return reported_cagr - haircut_pct
