import config


def test_reliability_config_present():
    assert 0 < config.COMMISSION_RATE < 0.01
    assert config.SLIPPAGE_BPS >= 0
    assert config.PIT_ANNUAL_LAG_DAYS == 90
    assert config.PIT_QUARTER_LAG_DAYS == 45
    assert config.OOS_FRACTION == 0.30
    assert config.MIN_DEFLATED_SR == 0.95
    assert config.PRICE_LIMIT_PCT == 0.30
    assert config.MIN_TRADE_VALUE_KRW == 100_000_000


def test_sell_tax_table_sorted_desc_by_date():
    dates = [d for d, _ in config.SELL_TAX_TABLE]
    assert dates == sorted(dates, reverse=True)
    assert config.SELL_TAX_TABLE[0][0] == '2025-01-01'


def test_tick_table_ascending_bounds():
    bounds = [b for b, _ in config.TICK_TABLE]
    assert bounds == sorted(bounds)
    assert config.TICK_TABLE[0] == (2_000, 1)
