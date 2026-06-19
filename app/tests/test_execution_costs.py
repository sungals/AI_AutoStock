import execution_model as em


def test_sell_tax_by_date():
    assert em.sell_tax_rate('2025-06-01') == 0.0015
    assert em.sell_tax_rate('2024-06-01') == 0.0018
    assert em.sell_tax_rate('2023-06-01') == 0.0020
    assert em.sell_tax_rate('2022-06-01') == 0.0023


def test_apply_costs_sell_includes_tax():
    r = em.apply_costs('sell', 10000, 10, '2025-06-01',
                       commission_rate=0.00015, slippage_bps=0)
    # gross = 100000, tax = 100000 * 0.0015 = 150, commission = 15
    assert abs(r['tax'] - 150) < 1e-6
    assert abs(r['commission'] - 15) < 1e-6
    assert r['net'] < r['gross']            # 매도 실수령 < 총액
    assert abs(r['net'] - (100000 - 15 - 150)) < 1e-6


def test_apply_costs_buy_no_tax():
    r = em.apply_costs('buy', 10000, 10, '2025-06-01',
                       commission_rate=0.00015, slippage_bps=0)
    assert r['tax'] == 0
    assert r['net'] > r['gross']            # 매수 실지불 > 총액(수수료 가산)
    assert abs(r['net'] - (100000 + 15)) < 1e-6


def test_slippage_unfavorable_direction():
    buy = em.apply_costs('buy', 10000, 1, '2025-06-01',
                         commission_rate=0, slippage_bps=10)
    sell = em.apply_costs('sell', 10000, 1, '2025-06-01',
                          commission_rate=0, slippage_bps=10)
    # 매수는 비싸게(+), 매도는 싸게(-) 체결
    assert buy['fill_price'] > 10000
    assert sell['fill_price'] < 10000
