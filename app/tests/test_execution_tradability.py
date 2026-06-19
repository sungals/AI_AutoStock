import execution_model as em


def test_round_to_tick():
    assert em.round_to_tick(1501.4) == 1501     # 2천 미만: 1원 단위
    assert em.round_to_tick(10003) == 10000     # 1만~2만: 10원
    assert em.round_to_tick(73210) == 73200     # 5만~20만: 100원
    assert em.round_to_tick(640400) == 640000   # 50만 이상: 1000원


def test_not_tradable_when_halted():
    ohlcv = {'open': 0, 'high': 0, 'low': 0, 'close': 0, 'volume': 0}
    assert em.is_tradable('buy', ohlcv, prev_close=10000) is False


def test_cannot_buy_at_limit_up_lock():
    # 점상한가(+30%): high==low==close==13000, 잠김. 거래대금은 유동성 임계 이상으로.
    ohlcv = {'open': 13000, 'high': 13000, 'low': 13000, 'close': 13000,
             'volume': 100000, 'value': 1_300_000_000}
    assert em.is_tradable('buy', ohlcv, prev_close=10000) is False
    # 같은 봉이라도 매도는 가능
    assert em.is_tradable('sell', ohlcv, prev_close=10000) is True


def test_cannot_sell_at_limit_down_lock():
    ohlcv = {'open': 7000, 'high': 7000, 'low': 7000, 'close': 7000,
             'volume': 1000, 'value': 7_000_000}
    assert em.is_tradable('sell', ohlcv, prev_close=10000) is False


def test_illiquid_excluded():
    ohlcv = {'open': 1000, 'high': 1010, 'low': 990, 'close': 1000,
             'volume': 100, 'value': 100_000}   # 거래대금 10만 << 1억
    assert em.is_tradable('buy', ohlcv, prev_close=1000) is False


def test_normal_bar_tradable():
    ohlcv = {'open': 10000, 'high': 10500, 'low': 9800, 'close': 10200,
             'volume': 50000, 'value': 510_000_000}
    assert em.is_tradable('buy', ohlcv, prev_close=10000) is True
