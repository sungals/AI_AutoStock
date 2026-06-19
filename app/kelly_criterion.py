"""Kelly Criterion 기반 포지션 크기 계산."""


def calculate_kelly_ratio(win_rate: float, avg_win: float, avg_loss: float,
                          fraction: float = 0.25) -> float:
    """분수 Kelly 비율. 과도한 배팅 방지를 위해 0~30%로 제한."""
    if avg_loss <= 0 or avg_win <= 0 or win_rate <= 0:
        return 0.0
    b = avg_win / avg_loss
    p = win_rate
    q = 1.0 - win_rate
    full_kelly = (b * p - q) / b
    kelly = max(0.0, min(full_kelly * fraction, 0.3))
    return round(kelly, 4)
