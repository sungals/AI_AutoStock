"""재무 지표 계산 (순수함수). 05-구현-가이드.md §2.3. Python 3.9 호환."""
from typing import Optional


def calc_per(market_cap: int, net_income: int) -> Optional[float]:
    if not market_cap or not net_income or net_income <= 0:
        return None
    return round(market_cap / net_income, 2)


def calc_pbr(market_cap: int, equity: int) -> Optional[float]:
    if not market_cap or not equity or equity <= 0:
        return None
    return round(market_cap / equity, 2)


def calc_roe(net_income: int, equity: int) -> Optional[float]:
    if net_income is None or not equity or equity <= 0:
        return None
    return round(net_income / equity * 100, 2)


def calc_debt_ratio(liabilities: int, equity: int) -> Optional[float]:
    if liabilities is None or not equity or equity <= 0:
        return None
    return round(liabilities / equity * 100, 2)
