import sqlite3
import point_in_time as pit


def _make_conn():
    conn = sqlite3.connect(':memory:')
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE financial_statements(
            corp_code TEXT, bsns_year TEXT, reprt_code TEXT, fs_div TEXT,
            sj_div TEXT, account_id TEXT, thstrm_amount INTEGER, disclosed_at TEXT)
    """)
    return conn


def test_estimate_annual_lag():
    # 2023 사업보고서(11011) → 2023-12-31 + 90일 ≈ 2024-03-31
    d = pit.estimate_disclosed_at('2023', '11011')
    assert d >= '2024-03-01'
    assert d <= '2024-04-15'


def test_estimate_quarter_lag():
    # 2024 1분기(11013) → 2024-03-31 + 45일 ≈ 2024-05-15
    d = pit.estimate_disclosed_at('2024', '11013')
    assert '2024-05-01' <= d <= '2024-05-31'


def test_no_lookahead_leak_with_explicit_disclosed_at():
    conn = _make_conn()
    # 2024 사업보고서가 2025-03-15에 공시됨
    conn.execute(
        "INSERT INTO financial_statements VALUES "
        "('00126380','2024','11011','CFS','IS','ifrs-full_Revenue',100,'2025-03-15')")
    # 2025-02-01 시점 백테스트에는 보이면 안 됨
    assert pit.get_financials_asof(conn, '00126380', '2025-02-01') == []
    # 2025-04-01 시점에는 보여야 함
    rows = pit.get_financials_asof(conn, '00126380', '2025-04-01')
    assert len(rows) == 1
    assert rows[0]['thstrm_amount'] == 100


def test_disclosed_at_fallback_when_null():
    conn = _make_conn()
    # disclosed_at이 NULL → estimate_disclosed_at(2023,11011) ≈ 2024-03-31 사용
    conn.execute(
        "INSERT INTO financial_statements VALUES "
        "('00126380','2023','11011','CFS','IS','ifrs-full_Revenue',100,NULL)")
    assert pit.get_financials_asof(conn, '00126380', '2024-01-01') == []
    rows = pit.get_financials_asof(conn, '00126380', '2024-06-01')
    assert len(rows) == 1
    # 채워진 disclosed_at은 추정값
    assert rows[0]['disclosed_at'] >= '2024-03-01'
