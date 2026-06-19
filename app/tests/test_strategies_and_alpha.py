"""value/turnaround 전략 + alpha 벤치마크 정교화 검증."""
import db_core
import backtester
import point_in_time


# ── PIT 지표가 가치/실적전환 신호를 올바로 산출하는지 ──

def test_metrics_value_stock(fundamentals_db):
    dbp, dates = fundamentals_db
    with db_core.get_connection(dbp) as conn:
        m = point_in_time.get_metrics_asof(conn, 'C000000', '2022-03-01',
                                           stock_code='000001')
    assert 4 <= m['per'] <= 6
    assert 0.7 <= m['pbr'] <= 0.9
    assert 14 <= m['roe'] <= 18
    assert m.get('opincome_turnaround') == 0


def test_metrics_turnaround_stock(fundamentals_db):
    dbp, dates = fundamentals_db
    with db_core.get_connection(dbp) as conn:
        m = point_in_time.get_metrics_asof(conn, 'C000003', '2022-03-01',
                                           stock_code='000004')
    assert m['opincome_turnaround'] == 1          # 전년 적자 → 당기 흑자
    assert m['revenue_growth_yoy'] >= 35          # 매출 급증


# ── 전략 종목 선택 ──

def test_value_select_picks_cheap_quality(fundamentals_db):
    dbp, dates = fundamentals_db
    with db_core.get_connection(dbp) as conn:
        picks = backtester._select(conn, 'value', '2022-03-01', None, 3, 'realistic')
    assert '000001' in picks and '000002' in picks   # 저평가 우량
    assert '000003' not in picks                     # 고평가 제외


def test_turnaround_select_top_is_turnaround(fundamentals_db):
    dbp, dates = fundamentals_db
    with db_core.get_connection(dbp) as conn:
        picks = backtester._select(conn, 'turnaround', '2022-03-01', None, 5, 'realistic')
    assert picks[0] == '000004'                       # 흑자전환주가 최상위


def test_unknown_strategy_raises(fundamentals_db):
    dbp, dates = fundamentals_db
    with db_core.get_connection(dbp) as conn:
        try:
            backtester._select(conn, 'nope', '2022-03-01', None, 3, 'realistic')
            assert False, "should raise"
        except ValueError:
            pass


# ── 백테스트가 펀더멘털 전략으로 실제 매매하는지 ──

def test_value_backtest_executes_trades(fundamentals_db):
    dbp, dates = fundamentals_db
    with db_core.get_connection(dbp) as conn:
        res = backtester.run_backtest(conn, 'value', dates[20], dates[-1],
                                      top_n=2, fill_model='realistic')
    assert res['n_trades'] > 0


# ── alpha = 전략 CAGR − 벤치마크 CAGR ──

def test_alpha_equals_cagr_minus_benchmark(fundamentals_db):
    dbp, dates = fundamentals_db
    with db_core.get_connection(dbp) as conn:
        res = backtester.run_backtest(conn, 'value', dates[20], dates[-1],
                                      top_n=2, fill_model='ideal')
        wdates = backtester._all_trade_dates(conn, dates[20], dates[-1])
        bench = backtester._benchmark_cagr(conn, wdates[0], wdates[-1], len(wdates))
    assert 'benchmark_cagr' in res
    assert abs(res['benchmark_cagr'] - round(bench, 4)) < 1e-6
    assert abs(res['alpha'] - round(res['cagr'] - bench, 4)) < 1e-6


def test_benchmark_equalweight_buyhold(fundamentals_db):
    dbp, dates = fundamentals_db
    with db_core.get_connection(dbp) as conn:
        bench = backtester._benchmark_cagr(conn, dates[0], dates[-1], len(dates))
    assert isinstance(bench, float)        # 동일가중 buy&hold CAGR 산출
