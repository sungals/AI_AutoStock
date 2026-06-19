"""체결·비용 모델 — 한국 시장의 현실적 거래비용과 체결 가능성.

순수함수 모듈 (DB 접근 없음). docs/backtest-reliability/00-스펙-설계.md §4.2.
Python 3.9 호환.
"""
from typing import Dict, Optional
import config


def sell_tax_rate(trade_date: str) -> float:
    """매도 시 증권거래세율(농특세 포함). 시점별 상이.

    Args:
        trade_date: 'YYYY-MM-DD'
    """
    for eff_date, rate in config.SELL_TAX_TABLE:   # 시행일 내림차순
        if trade_date >= eff_date:
            return rate
    return config.SELL_TAX_TABLE[-1][1]


def apply_costs(side: str, price: float, qty: int, trade_date: str,
                commission_rate: float, slippage_bps: float) -> Dict[str, float]:
    """매수/매도 체결 시 비용을 반영한 실수령/실지불 금액 계산.

    - 공통: 수수료(commission_rate, 양방향), 슬리피지(불리한 방향)
    - 매도: + 증권거래세 sell_tax_rate(trade_date)

    Returns:
        {'fill_price', 'gross', 'commission', 'tax', 'slippage', 'net'}
        net = 매수 시 실지불(>gross), 매도 시 실수령(<gross)
    """
    slip_per_share = price * (slippage_bps / 10000.0)
    if side == 'buy':
        fill_price = price + slip_per_share
    else:
        fill_price = price - slip_per_share

    gross = fill_price * qty
    commission = gross * commission_rate
    tax = gross * sell_tax_rate(trade_date) if side == 'sell' else 0.0

    if side == 'buy':
        net = gross + commission                # 실지불
    else:
        net = gross - commission - tax          # 실수령

    return {
        'fill_price': fill_price,
        'gross': gross,
        'commission': commission,
        'tax': tax,
        'slippage': slip_per_share * qty,
        'net': net,
    }


def round_to_tick(price: float) -> int:
    """한국 주식 호가단위로 반올림 (config.TICK_TABLE, 2023.1 개편 기준)."""
    p = float(price)
    for upper, tick in config.TICK_TABLE:
        if p < upper:
            return int(round(p / tick) * tick)
    # 표를 벗어나는 초고가: 마지막 단위 적용
    last_tick = config.TICK_TABLE[-1][1]
    return int(round(p / last_tick) * last_tick)


def is_tradable(side: str, ohlcv: Dict, prev_close: int,
                min_value_krw: Optional[int] = None) -> bool:
    """해당 봉에서 side 방향 체결이 현실적으로 가능한지.

    False 조건:
      - 거래정지/거래없음: volume <= 0
      - 점상한가 매수 불가: side=='buy' & high==low & close>=상한가
      - 점하한가 매도 불가: side=='sell' & high==low & close<=하한가
      - 유동성 부족: 당일 거래대금 < min_value_krw
    """
    if min_value_krw is None:
        min_value_krw = config.MIN_TRADE_VALUE_KRW
    if not ohlcv or ohlcv.get('volume', 0) <= 0:
        return False

    high = ohlcv.get('high', 0)
    low = ohlcv.get('low', 0)
    close = ohlcv.get('close', 0)

    limit_up = prev_close * (1 + config.PRICE_LIMIT_PCT)
    limit_down = prev_close * (1 - config.PRICE_LIMIT_PCT)
    locked = (high == low)   # 하루종일 단일가 = 점상/점하한 잠김

    if side == 'buy' and locked and close >= limit_up * 0.999:
        return False
    if side == 'sell' and locked and close <= limit_down * 1.001:
        return False

    value = ohlcv.get('value') or (close * ohlcv.get('volume', 0))
    if value < min_value_krw:
        return False

    return True
