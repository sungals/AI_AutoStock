"""포트폴리오 리스크 가드 순수 함수."""
from datetime import date


def check_trailing_stop(entry_price: float, highest_price: float,
                        current_price: float, trail_pct: float = 0.08) -> bool:
    if highest_price <= 0:
        return False
    return (highest_price - current_price) / highest_price >= trail_pct


def check_timeout_exit(entry_date: str, current_date: str,
                       max_days: int = 90) -> bool:
    entry = date.fromisoformat(entry_date)
    current = date.fromisoformat(current_date)
    return (current - entry).days >= max_days


def check_vix_defensive(vix: float, threshold: float = 30.0) -> bool:
    return vix > threshold


def check_daily_loss_limit(daily_pnl: float, portfolio_value: float,
                           limit_pct: float = 0.03) -> bool:
    if portfolio_value <= 0:
        return False
    return daily_pnl / portfolio_value <= -limit_pct
