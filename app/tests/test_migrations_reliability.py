import db_core


def _cols(conn, table):
    return [r[1] for r in conn.execute("PRAGMA table_info(%s)" % table).fetchall()]


def test_reliability_columns_added(tmp_path):
    dbp = str(tmp_path / 'q.db')
    db_core.init_db(dbp)
    with db_core.get_connection(dbp) as conn:
        assert 'disclosed_at' in _cols(conn, 'financial_statements')
        for c in ('is_cagr', 'oos_cagr', 'deflated_sharpe', 'cost_bps',
                  'gate_passed', 'gate_reason'):
            assert c in _cols(conn, 'simulation_runs')
        for c in ('slippage_bps', 'tax_rate', 'fill_model'):
            assert c in _cols(conn, 'backtest_runs')


def test_migration_idempotent(tmp_path):
    dbp = str(tmp_path / 'q.db')
    db_core.init_db(dbp)
    db_core.init_db(dbp)   # 두 번 호출해도 에러 없음
    with db_core.get_connection(dbp) as conn:
        assert 'disclosed_at' in _cols(conn, 'financial_statements')


def test_base_tables_exist(tmp_path):
    dbp = str(tmp_path / 'q.db')
    db_core.init_db(dbp)
    with db_core.get_connection(dbp) as conn:
        names = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    for t in ('companies', 'price_data', 'financial_statements',
              'calculated_metrics', 'screening_results', 'simulation_runs',
              'backtest_runs', 'backtest_metrics', 'algo_params'):
        assert t in names
