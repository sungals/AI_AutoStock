"""과최적화 방지 — IS/OOS 분리 + Deflated Sharpe Ratio + 반영 게이트.

docs/backtest-reliability/00-스펙-설계.md §4.3. Python 3.9 호환.
의존성은 numpy만 사용(scipy 미사용 — 정규분포 CDF/inverse-CDF 직접 구현).
"""
from typing import Dict, Tuple
from datetime import date, timedelta
import math
import numpy as np
import config

_EULER_GAMMA = 0.5772156649015329


def split_is_oos(window_start: str, window_end: str,
                 oos_fraction: float = None) -> Tuple[Tuple[str, str], Tuple[str, str]]:
    """기간을 앞 IS / 뒤 OOS 로 분할 (일수 비례).

    Returns:
        ((is_start, is_end), (oos_start, oos_end)), 경계 연속(is_end == oos_start).
    """
    if oos_fraction is None:
        oos_fraction = config.OOS_FRACTION
    start = date.fromisoformat(window_start)
    end = date.fromisoformat(window_end)
    total_days = (end - start).days
    is_days = int(round(total_days * (1.0 - oos_fraction)))
    split = start + timedelta(days=is_days)
    split_s = split.isoformat()
    return ((window_start, split_s), (split_s, window_end))


def _norm_cdf(x: float) -> float:
    """표준정규 누적분포함수 (erf 기반)."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _norm_ppf(p: float) -> float:
    """표준정규 역누적분포(inverse CDF). Acklam 근사."""
    if p <= 0.0:
        return -np.inf
    if p >= 1.0:
        return np.inf
    a = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
         1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00]
    b = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
         6.680131188771972e+01, -1.328068155288572e+01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
         -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00,
         3.754408661907416e+00]
    plow, phigh = 0.02425, 1 - 0.02425
    if p < plow:
        q = math.sqrt(-2 * math.log(p))
        return (((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / \
               ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    if p > phigh:
        q = math.sqrt(-2 * math.log(1 - p))
        return -(((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / \
               ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    q = p - 0.5
    r = q * q
    return (((((a[0]*r+a[1])*r+a[2])*r+a[3])*r+a[4])*r+a[5])*q / \
           (((((b[0]*r+b[1])*r+b[2])*r+b[3])*r+b[4])*r+1)


def _expected_max_sharpe(n_trials: int) -> float:
    """N개 독립 시도 시 기대 최대 Sharpe (표준화). Bailey & López de Prado."""
    if n_trials <= 1:
        return 0.0
    return ((1 - _EULER_GAMMA) * _norm_ppf(1 - 1.0 / n_trials)
            + _EULER_GAMMA * _norm_ppf(1 - 1.0 / (n_trials * math.e)))


def deflated_sharpe_ratio(observed_sharpe: float, n_trials: int, n_obs: int,
                          skew: float = 0.0, kurt: float = 3.0) -> float:
    """Deflated Sharpe Ratio (0~1).

    n_trials개 전략을 시도했을 때 관측 Sharpe가 우연이 아닐 확률.
    다중검정으로 부풀려진 기대 최대 Sharpe를 차감해 보정한다.
    observed_sharpe, expected_max는 '구간당' 단위로 일관 가정(여기선 단순화).
    """
    if n_obs <= 1:
        return 0.0
    sr0 = _expected_max_sharpe(n_trials)
    # SR 추정량의 표준오차 (비정규성 보정 포함)
    denom = math.sqrt(max(1e-12,
                          1 - skew * observed_sharpe
                          + ((kurt - 1) / 4.0) * observed_sharpe ** 2))
    se = denom / math.sqrt(n_obs - 1)
    z = (observed_sharpe - sr0) / se
    return _norm_cdf(z)


def passes_gate(is_metrics: Dict, oos_metrics: Dict, deflated_sr: float,
                min_dsr: float = None) -> Tuple[bool, str]:
    """옵티마이저 반영 게이트.

    통과 조건(전부 충족):
      - oos_cagr > 0
      - oos_sharpe >= is_sharpe * 0.5  (IS 대비 과도한 붕괴 없음)
      - deflated_sr >= min_dsr
    """
    if min_dsr is None:
        min_dsr = config.MIN_DEFLATED_SR

    oos_cagr = oos_metrics.get('cagr', 0.0)
    oos_sharpe = oos_metrics.get('sharpe', 0.0)
    is_sharpe = is_metrics.get('sharpe', 0.0)

    if oos_cagr <= 0:
        return False, 'oos_cagr<=0 (OOS 수익 없음)'
    if oos_sharpe < is_sharpe * 0.5:
        return False, 'oos_sharpe collapse (IS 대비 50%% 미만: %.2f < %.2f)' % (
            oos_sharpe, is_sharpe * 0.5)
    if deflated_sr < min_dsr:
        return False, 'deflated_sr too low (%.3f < %.3f)' % (deflated_sr, min_dsr)
    return True, 'passed'
