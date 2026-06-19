import sqlite3
import bias_report as br


def _make_conn():
    conn = sqlite3.connect(':memory:')
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE price_data(
            stock_code TEXT, trade_date TEXT, close INTEGER)
    """)
    return conn


def _add_series(conn, code, last_date):
    # 단순화: 종목별 마지막 거래일만 의미 있게 둠
    conn.execute("INSERT INTO price_data VALUES (?,?,?)", (code, '2020-01-02', 1000))
    conn.execute("INSERT INTO price_data VALUES (?,?,?)", (code, last_date, 1100))


def test_no_delisting_zero_haircut():
    conn = _make_conn()
    for c in ('A', 'B', 'C'):
        _add_series(conn, c, '2020-12-30')   # 전부 끝까지 생존
    r = br.estimate_survivorship_bias(conn, '2020-01-01', '2020-12-30')
    assert r['delisted_ratio'] == 0.0
    assert r['estimated_cagr_haircut_pct'] == 0.0


def test_some_delisting_positive_haircut():
    conn = _make_conn()
    _add_series(conn, 'A', '2020-12-30')      # 생존
    _add_series(conn, 'B', '2020-12-30')      # 생존
    _add_series(conn, 'C', '2020-06-01')      # 중도 소멸
    _add_series(conn, 'D', '2020-05-01')      # 중도 소멸
    r = br.estimate_survivorship_bias(conn, '2020-01-01', '2020-12-30')
    assert r['delisted_ratio'] == 0.5         # 4종목 중 2종목 소멸
    assert r['estimated_cagr_haircut_pct'] > 0
    assert 'warning' in r and r['warning']


def test_apply_haircut_lowers_cagr():
    assert br.apply_haircut(20.0, 5.0) == 15.0
    assert br.apply_haircut(20.0, 0.0) == 20.0
