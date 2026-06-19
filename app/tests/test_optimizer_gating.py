"""Task 10: algo_optimizer가 gate_passed=1 run만 반영하는지."""
import db_core
import algo_optimizer


def _insert_run(conn, strategy, oos_cagr, dsr, gate_passed, reason):
    conn.execute(
        """INSERT INTO simulation_runs
           (batch_id, strategy, risk_profile, cagr, oos_cagr, deflated_sharpe,
            gate_passed, gate_reason, status)
           VALUES ('B','%s','moderate',?,?,?,?,?, 'ok')""" % strategy,
        (oos_cagr, oos_cagr, dsr, gate_passed, reason))


def test_only_gate_passed_params_applied(tmp_path):
    dbp = str(tmp_path / 'q.db')
    db_core.init_db(dbp)
    with db_core.get_connection(dbp) as conn:
        _insert_run(conn, 'momentum', 30.0, 0.40, 0, 'deflated_sr too low')  # 탈락(높은 cagr이지만)
        _insert_run(conn, 'momentum', 12.0, 0.98, 1, 'passed')              # 통과
        _insert_run(conn, 'value',    18.0, 0.99, 1, 'passed')              # 통과(최고 oos)

    with db_core.get_connection(dbp) as conn:
        summary = algo_optimizer.apply_optimal_params(conn, batch_id='B')

    assert summary['applied'] is True
    assert summary['skipped'] == 1
    # 반영된 best는 gate 통과 중 oos_cagr 최고('value', 18.0) — 탈락한 30.0이 아님
    assert summary['best_strategy'] == 'value'
    with db_core.get_connection(dbp) as conn:
        params = conn.execute("SELECT * FROM algo_params").fetchall()
    assert len(params) >= 1


def test_no_params_when_all_fail(tmp_path):
    dbp = str(tmp_path / 'q.db')
    db_core.init_db(dbp)
    with db_core.get_connection(dbp) as conn:
        _insert_run(conn, 'momentum', 30.0, 0.40, 0, 'deflated_sr too low')
        _insert_run(conn, 'value', 25.0, 0.50, 0, 'oos_sharpe collapse')
    with db_core.get_connection(dbp) as conn:
        summary = algo_optimizer.apply_optimal_params(conn, batch_id='B')
    assert summary['applied'] is False
    assert summary['skipped'] == 2
    with db_core.get_connection(dbp) as conn:
        assert conn.execute("SELECT COUNT(*) c FROM algo_params").fetchone()['c'] == 0
