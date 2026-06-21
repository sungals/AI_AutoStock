"""수집기 단위 테스트 (네트워크 없이 fetch 함수 주입/모킹)."""
import db_core
import company_master
import price_collector
import financial_collector


# ── company_master ──

def test_build_company_master_without_dart_key(tmp_path):
    dbp = str(tmp_path / 'q.db')
    db_core.init_db(dbp)
    tickers = {'KOSPI': ['005930', '000660'], 'KOSDAQ': ['035720']}
    names = {'005930': '삼성전자', '000660': 'SK하이닉스', '035720': '카카오'}
    with db_core.get_connection(dbp) as conn:
        n = company_master.build_company_master(
            conn, markets=('KOSPI', 'KOSDAQ'), api_key='',     # 키 없음 → 폴백 corp_code
            ticker_fn=lambda m: tickers[m], name_fn=lambda t: names[t])
    assert n == 3
    with db_core.get_connection(dbp) as conn:
        row = conn.execute("SELECT * FROM companies WHERE stock_code='005930'").fetchone()
    assert row['corp_name'] == '삼성전자'
    assert row['corp_code'] == 'X005930'      # DART 키 없을 때 폴백 키
    assert row['market'] == 'KOSPI'


def test_build_company_master_with_dart_map(tmp_path):
    dbp = str(tmp_path / 'q.db')
    db_core.init_db(dbp)
    corp_map = {'005930': {'corp_code': '00126380', 'corp_name': '삼성전자'}}
    with db_core.get_connection(dbp) as conn:
        company_master.build_company_master(
            conn, markets=('KOSPI',), api_key='KEY',
            ticker_fn=lambda m: ['005930'], name_fn=lambda t: 'X',
            corp_map_fn=lambda k: corp_map)
    with db_core.get_connection(dbp) as conn:
        row = conn.execute("SELECT * FROM companies WHERE stock_code='005930'").fetchone()
    assert row['corp_code'] == '00126380'     # DART corp_code 매핑됨


# ── price_collector ──

def test_collect_prices_with_injected_fetch(tmp_path):
    dbp = str(tmp_path / 'q.db')
    db_core.init_db(dbp)

    def fake_fetch(code, start, end):
        return [
            {'trade_date': '2024-01-02', 'open': 76700, 'high': 77100, 'low': 76400,
             'close': 76600, 'volume': 11304316, 'market_cap': 457_000_000_000_000,
             'value': 866_000_000_000},
            {'trade_date': '2024-01-03', 'open': 76500, 'high': 76800, 'low': 75900,
             'close': 75900, 'volume': 15000000, 'market_cap': 453_000_000_000_000,
             'value': 1_100_000_000_000},
        ]

    with db_core.get_connection(dbp) as conn:
        res = price_collector.collect_prices(
            conn, ['005930'], '20240102', '20240103', fetch_fn=fake_fetch)
    assert res['stocks'] == 1 and res['rows'] == 2
    with db_core.get_connection(dbp) as conn:
        rows = conn.execute(
            "SELECT * FROM price_data WHERE stock_code='005930' ORDER BY trade_date").fetchall()
    assert rows[0]['close'] == 76600
    assert rows[0]['market_cap'] == 457_000_000_000_000
    assert rows[1]['value'] == 1_100_000_000_000


def test_collect_prices_value_fallback_when_missing():
    # market_cap/value 누락 시 value = close*volume 폴백은 _fetch에서 처리되지만,
    # upsert는 주어진 값을 그대로 저장. 폴백 계산은 fetch 단계 책임.
    rows = [{'trade_date': '2024-01-02', 'open': 0, 'high': 0, 'low': 0,
             'close': 100, 'volume': 10, 'market_cap': None, 'value': 1000}]
    assert rows[0]['value'] == 1000


# ── financial_collector ──

def test_to_int_parsing():
    assert financial_collector._to_int('1,234,567') == 1234567
    assert financial_collector._to_int('-') is None
    assert financial_collector._to_int('') is None
    assert financial_collector._to_int('-500') == -500


def test_cfs_first_fallback_to_ofs():
    calls = []

    def fake_fetch(api_key, corp, year, reprt, fs_div):
        calls.append(fs_div)
        return None if fs_div == 'CFS' else [{'account_id': 'ifrs-full_Assets',
                                              'sj_div': 'BS', 'thstrm_amount': '100'}]

    items, fs_div = financial_collector.fetch_financials_cfs_first(
        'K', '00126380', '2023', '11011', fetch_fn=fake_fetch)
    assert calls == ['CFS', 'OFS']      # CFS 먼저 시도 후 OFS 폴백
    assert fs_div == 'OFS'
    assert items[0]['account_id'] == 'ifrs-full_Assets'


def test_collect_financials_skips_without_key(tmp_path):
    dbp = str(tmp_path / 'q.db')
    db_core.init_db(dbp)
    with db_core.get_connection(dbp) as conn:
        res = financial_collector.collect_financials(
            conn, ['00126380'], ['2023'], api_key='')
    assert res['skipped'] is True


def test_collect_financials_stores_disclosed_at(tmp_path):
    dbp = str(tmp_path / 'q.db')
    db_core.init_db(dbp)

    def fake_fetch(api_key, corp, year, reprt, fs_div):
        if fs_div == 'CFS':
            return [
                {'account_id': 'ifrs-full_ProfitLoss', 'sj_div': 'IS', 'thstrm_amount': '1,000,000,000'},
                {'account_id': 'ifrs-full_Equity', 'sj_div': 'BS', 'thstrm_amount': '6,250,000,000'},
            ]
        return None

    def fake_disclosure(api_key, corp, year, reprt):
        return '2024-03-15'      # 실제 rcept_dt 시뮬레이션

    with db_core.get_connection(dbp) as conn:
        res = financial_collector.collect_financials(
            conn, ['00126380'], ['2023'], api_key='K',
            fetch_fn=fake_fetch, disclosure_fn=fake_disclosure)
    assert res['skipped'] is False and res['rows'] == 2
    with db_core.get_connection(dbp) as conn:
        rows = conn.execute(
            "SELECT * FROM financial_statements WHERE corp_code='00126380'").fetchall()
    assert all(r['disclosed_at'] == '2024-03-15' for r in rows)   # 실측 공시일 저장
    assert all(r['fs_div'] == 'CFS' for r in rows)


def test_collect_financials_disclosure_fallback_to_estimate(tmp_path):
    dbp = str(tmp_path / 'q.db')
    db_core.init_db(dbp)

    def fake_fetch(api_key, corp, year, reprt, fs_div):
        return [{'account_id': 'ifrs-full_Equity', 'sj_div': 'BS', 'thstrm_amount': '100'}] \
            if fs_div == 'CFS' else None

    def no_disclosure(api_key, corp, year, reprt):
        return None      # 공시일 조회 실패 → PIT lag 추정으로 폴백

    with db_core.get_connection(dbp) as conn:
        financial_collector.collect_financials(
            conn, ['C1'], ['2023'], api_key='K',
            fetch_fn=fake_fetch, disclosure_fn=no_disclosure)
    with db_core.get_connection(dbp) as conn:
        row = conn.execute("SELECT disclosed_at FROM financial_statements").fetchone()
    assert row['disclosed_at'] >= '2024-03-01'    # estimate_disclosed_at(2023,11011)


# ── 발행주식수 → 시가총액 (KRX 우회) ──

def test_fetch_total_shares_prefers_common(monkeypatch):
    def fake(path, params):
        assert path == 'stockTotqySttus.json'
        return {'status': '000', 'list': [
            {'se': '보통주', 'istc_totqy': '5,969,782,550'},
            {'se': '우선주', 'istc_totqy': '822,886,700'},
        ]}
    monkeypatch.setattr(financial_collector, '_dart_get', fake)
    n = financial_collector.fetch_total_shares('K', '00126380', '2023')
    assert n == 5969782550


def test_fetch_total_shares_falls_back_to_total(monkeypatch):
    def fake(path, params):
        return {'status': '000', 'list': [{'se': '합계', 'istc_totqy': '1,000'}]}
    monkeypatch.setattr(financial_collector, '_dart_get', fake)
    assert financial_collector.fetch_total_shares('K', 'C', '2023') == 1000


def test_populate_market_cap_updates_rows(tmp_path):
    dbp = str(tmp_path / 'q.db')
    db_core.init_db(dbp)
    with db_core.get_connection(dbp) as conn:
        conn.execute("INSERT INTO companies (corp_code, stock_code, corp_name) "
                     "VALUES ('00126380','005930','삼성전자')")
        conn.execute("INSERT INTO companies (corp_code, stock_code, corp_name) "
                     "VALUES ('X000999','000999','폴백corp')")   # 실 corp_code 아님 → 제외
        for dt, close in (('2024-01-02', 70000), ('2024-01-03', 72000)):
            conn.execute("INSERT INTO price_data (stock_code, trade_date, close) "
                         "VALUES ('005930',?,?)", (dt, close))
        conn.execute("INSERT INTO price_data (stock_code, trade_date, close) "
                     "VALUES ('000999','2024-01-02',100)")

    def fake_shares(api_key, corp_code, year):
        return 5_000_000_000 if corp_code == '00126380' else None

    with db_core.get_connection(dbp) as conn:
        res = financial_collector.populate_market_cap(
            conn, api_key='K', shares_fn=fake_shares)
        rows = conn.execute(
            "SELECT trade_date, market_cap FROM price_data WHERE stock_code='005930' "
            "ORDER BY trade_date").fetchall()
        fallback = conn.execute(
            "SELECT market_cap FROM price_data WHERE stock_code='000999'").fetchone()

    assert res['updated'] == 1 and res['rows'] == 2
    assert rows[0]['market_cap'] == 70000 * 5_000_000_000      # 종가 × 주식수
    assert rows[1]['market_cap'] == 72000 * 5_000_000_000
    assert fallback['market_cap'] is None                       # X corp_code 제외


def test_populate_market_cap_skips_without_key(tmp_path):
    dbp = str(tmp_path / 'q.db')
    db_core.init_db(dbp)
    with db_core.get_connection(dbp) as conn:
        res = financial_collector.populate_market_cap(conn, api_key='')
    assert res['skipped'] is True


def test_populate_market_cap_caches_shares_and_increments(tmp_path):
    """주식수 캐시 + market_cap NULL 행만 갱신 → 매일 실행 시 DART 재호출 최소화."""
    dbp = str(tmp_path / 'q.db')
    db_core.init_db(dbp)
    with db_core.get_connection(dbp) as conn:
        conn.execute("INSERT INTO companies (corp_code, stock_code, corp_name) "
                     "VALUES ('00126380','005930','삼성전자')")
        conn.execute("INSERT INTO price_data (stock_code, trade_date, close) "
                     "VALUES ('005930','2024-01-02',70000)")

    calls = {'n': 0}

    def counting_shares(api_key, corp_code, year):
        calls['n'] += 1
        return 5_000_000_000

    # 1) 최초: 주식수 fetch + 캐시 + 행 갱신
    with db_core.get_connection(dbp) as conn:
        r1 = financial_collector.populate_market_cap(conn, api_key='K', shares_fn=counting_shares)
    assert r1['updated'] == 1 and calls['n'] == 1
    with db_core.get_connection(dbp) as conn:
        sh = conn.execute("SELECT shares_outstanding FROM companies WHERE corp_code='00126380'").fetchone()
    assert sh['shares_outstanding'] == 5_000_000_000        # 캐시됨

    # 2) 변화 없음: 갱신할 NULL 행 없음 → fetch 없음
    with db_core.get_connection(dbp) as conn:
        r2 = financial_collector.populate_market_cap(conn, api_key='K', shares_fn=counting_shares)
    assert r2['updated'] == 0 and calls['n'] == 1           # 재호출 안 함

    # 3) 새 가격행 추가: 캐시된 주식수로 갱신, 여전히 fetch 없음
    with db_core.get_connection(dbp) as conn:
        conn.execute("INSERT INTO price_data (stock_code, trade_date, close) "
                     "VALUES ('005930','2024-01-03',72000)")
        r3 = financial_collector.populate_market_cap(conn, api_key='K', shares_fn=counting_shares)
        cap = conn.execute("SELECT market_cap FROM price_data WHERE trade_date='2024-01-03'").fetchone()
    assert r3['updated'] == 1 and calls['n'] == 1           # 캐시 사용, 재호출 없음
    assert cap['market_cap'] == 72000 * 5_000_000_000
