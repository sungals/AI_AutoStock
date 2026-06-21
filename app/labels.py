"""표시용 한글 라벨 매핑 — 전략 키/추천 등급을 한글로.

DB·API·링크 파라미터는 영문 키를 그대로 쓰고, 화면 표시에만 사용한다.
00-프로젝트-개요.md의 11종 전략 명칭 기준. Python 3.9 호환.
"""

STRATEGY_LABELS = {
    'all': '전체',
    'turnaround': '실적 전환주',
    'value': '가치주',
    'momentum': '모멘텀',
    'sector': '테마·업종',
    'trend': '추세 추종',
    'mean_revert': '평균 회귀',
    'event': '이벤트',
    'volatility': '변동성 돌파',
    'flow': '수급',
    'quality_lowvol': '퀄리티·저변동',
    'guru': '거장 필터',
}

RECOMMENDATION_LABELS = {
    'STRONG_BUY': '적극 매수',
    'BUY': '매수',
    'HOLD': '보유',
    'SELL': '매도',
    'STRONG_SELL': '적극 매도',
}


def strategy_ko(key):
    """전략 키 → 한글 라벨. 미등록/빈값이면 원본 또는 '-'."""
    if not key:
        return '-'
    return STRATEGY_LABELS.get(key, key)


def recommendation_ko(key):
    """추천 등급 → 한글 라벨. 미등록/빈값이면 원본 또는 '-'."""
    if not key:
        return '-'
    return RECOMMENDATION_LABELS.get(key, key)
