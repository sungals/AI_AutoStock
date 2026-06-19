"""Task 9: simulation_runner가 IS/OOS·Deflated Sharpe·gate를 기록하는지."""
import db_core
import simulation_runner


def test_run_batch_records_reliability_metrics(seeded_db):
    dbp, dates = seeded_db
    with db_core.get_connection(dbp) as conn:
        res = simulation_runner.run_batch(
            conn, dates[0], dates[-1], n=6)
    assert res['completed'] > 0
    with db_core.get_connection(dbp) as conn:
        rows = conn.execute(
            "SELECT oos_cagr, deflated_sharpe, gate_passed, is_cagr FROM simulation_runs"
        ).fetchall()
    assert len(rows) >= 1
    for r in rows:
        assert r['oos_cagr'] is not None
        assert r['deflated_sharpe'] is not None
        assert r['gate_passed'] in (0, 1)
        assert r['is_cagr'] is not None
