"""Phase 6: 매크로 데이터 저장과 시장 국면 감지."""
import db_core
import macro_data


def test_upsert_macro_price_and_detect_bull_regime(tmp_path):
    dbp = str(tmp_path / 'q.db')
    db_core.init_db(dbp)
    with db_core.get_connection(dbp) as conn:
        for i in range(60):
            close = 100 + i * 0.2
            macro_data.upsert_macro_price(
                conn, 'KS11', 'KOSPI', 'index', '2024-01-%02d' % (i + 1),
                close, 0.1)
        macro_data.upsert_macro_price(conn, '^VIX', 'VIX', 'index', '2024-03-01', 18.0, -1.0)
        regime = macro_data.detect_market_regime(conn)

    assert regime == 'bull'


def test_detect_bear_regime_when_vix_high(tmp_path):
    dbp = str(tmp_path / 'q.db')
    db_core.init_db(dbp)
    with db_core.get_connection(dbp) as conn:
        for i in range(60):
            macro_data.upsert_macro_price(
                conn, 'KS11', 'KOSPI', 'index', '2024-01-%02d' % (i + 1),
                100.0, 0.0)
        macro_data.upsert_macro_price(conn, '^VIX', 'VIX', 'index', '2024-03-01', 35.0, 10.0)
        regime = macro_data.detect_market_regime(conn)

    assert regime == 'bear'


def test_fetch_macro_data_with_injected_fetcher(tmp_path):
    dbp = str(tmp_path / 'q.db')
    db_core.init_db(dbp)

    def fake_fetch(symbol):
        return [
            {'trade_date': '2024-01-01', 'close': 100.0},
            {'trade_date': '2024-01-02', 'close': 105.0},
        ]

    with db_core.get_connection(dbp) as conn:
        res = macro_data.fetch_macro_data(conn, symbols={'TEST': ('테스트', 'index')},
                                          fetch_fn=fake_fetch)
        row = conn.execute(
            "SELECT close, change_pct FROM macro_prices WHERE symbol='TEST'"
        ).fetchone()

    assert res['rows'] == 1
    assert row['close'] == 105.0
    assert row['change_pct'] == 5.0
