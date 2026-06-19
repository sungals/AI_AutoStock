import validation_harness as vh


# ── Task 7: IS/OOS 분리 ──

def test_split_is_oos_boundaries():
    (is_s, is_e), (oos_s, oos_e) = vh.split_is_oos('2020-01-01', '2021-01-01', 0.30)
    assert is_s == '2020-01-01'
    assert oos_e == '2021-01-01'
    assert is_e == oos_s            # 경계 연속
    assert is_s < is_e < oos_e      # OOS는 뒤쪽


def test_split_is_oos_fraction_roughly_30pct():
    (is_s, is_e), (oos_s, oos_e) = vh.split_is_oos('2020-01-01', '2020-12-31', 0.30)
    from datetime import date
    total = (date.fromisoformat(oos_e) - date.fromisoformat(is_s)).days
    oos = (date.fromisoformat(oos_e) - date.fromisoformat(oos_s)).days
    assert 0.25 <= oos / total <= 0.35


# ── Task 8: Deflated Sharpe + 게이트 ──

def test_deflated_sharpe_penalizes_many_trials():
    sr_few = vh.deflated_sharpe_ratio(2.0, n_trials=1, n_obs=252)
    sr_many = vh.deflated_sharpe_ratio(2.0, n_trials=10000, n_obs=252)
    assert 0.0 <= sr_many <= 1.0
    assert 0.0 <= sr_few <= 1.0
    assert sr_many < sr_few           # 시도 많을수록 보정 강함


def test_deflated_sharpe_high_sharpe_high_confidence():
    # 단일 시도 + 매우 높은 Sharpe → 높은 신뢰
    sr = vh.deflated_sharpe_ratio(3.0, n_trials=1, n_obs=500)
    assert sr > 0.9


def test_gate_rejects_oos_collapse():
    ok, reason = vh.passes_gate(
        is_metrics={'sharpe': 2.0, 'cagr': 30.0},
        oos_metrics={'sharpe': 0.1, 'cagr': -5.0},
        deflated_sr=0.99)
    assert ok is False
    assert 'oos' in reason.lower() or 'cagr' in reason.lower()


def test_gate_rejects_low_deflated_sharpe():
    ok, reason = vh.passes_gate(
        is_metrics={'sharpe': 2.0, 'cagr': 30.0},
        oos_metrics={'sharpe': 1.8, 'cagr': 25.0},
        deflated_sr=0.50)
    assert ok is False
    assert 'deflated' in reason.lower() or 'dsr' in reason.lower()


def test_gate_passes_robust_strategy():
    ok, reason = vh.passes_gate(
        is_metrics={'sharpe': 1.5, 'cagr': 20.0},
        oos_metrics={'sharpe': 1.3, 'cagr': 18.0},
        deflated_sr=0.99)
    assert ok is True
