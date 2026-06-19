"""Task 12: 리포트에 생존편향 경고 + OOS/Deflated Sharpe가 노출되는지."""
import db_core
import reliability_report


def test_report_contains_warning_and_metrics(seeded_db):
    dbp, dates = seeded_db
    import simulation_runner
    with db_core.get_connection(dbp) as conn:
        simulation_runner.run_batch(conn, dates[0], dates[-1], n=6)
    with db_core.get_connection(dbp) as conn:
        report = reliability_report.build_report(conn, dates[0], dates[-1])

    assert 'survivorship' in report
    assert 'delisted_ratio' in report['survivorship']
    assert 'concentration' in report
    assert 'universe_size' in report['concentration']
    assert 'runs_summary' in report
    assert report['runs_summary']['total'] >= 1
    # 각 run 요약에 deflated_sharpe, oos_cagr 포함
    assert 'best_gate_passed' in report
    assert 'text' in report and isinstance(report['text'], str)


def test_report_survivorship_warning_when_delisted(tmp_path):
    dbp = str(tmp_path / 'q.db')
    db_core.init_db(dbp)
    with db_core.get_connection(dbp) as conn:
        # 종목 A는 끝까지, B는 중도 소멸
        for dt, codes in [('2022-01-03', ['A', 'B']), ('2022-06-01', ['A'])]:
            for c in codes:
                conn.execute("INSERT INTO price_data (stock_code, trade_date, close) "
                             "VALUES (?,?,?)", (c, dt, 1000))
    with db_core.get_connection(dbp) as conn:
        report = reliability_report.build_report(conn, '2022-01-03', '2022-06-01')
    assert report['survivorship']['delisted_ratio'] > 0
    assert '⚠️' in report['text']


def test_report_warns_on_small_or_sector_concentrated_universe(tmp_path):
    dbp = str(tmp_path / 'q.db')
    db_core.init_db(dbp)
    with db_core.get_connection(dbp) as conn:
        for code, sector in [('A', '반도체'), ('B', '반도체'), ('C', '바이오')]:
            conn.execute(
                "INSERT INTO companies (corp_code, stock_code, corp_name, sector) "
                "VALUES (?,?,?,?)",
                ('C' + code, code, 'CO' + code, sector))
            conn.execute(
                "INSERT INTO price_data (stock_code, trade_date, close) VALUES (?,?,?)",
                (code, '2024-01-02', 1000))

    with db_core.get_connection(dbp) as conn:
        report = reliability_report.build_report(conn, '2024-01-02', '2024-01-02')

    assert report['concentration']['universe_size'] == 3
    assert report['concentration']['max_sector'] == '반도체'
    assert report['concentration']['max_sector_weight'] == 0.6667
    assert '표본/집중 리스크' in report['text']
    assert '섹터 집중 리스크' in report['text']
