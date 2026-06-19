"""Phase 7: 융합 시그널."""
import db_core
import fusion_analyzer


def test_calculate_fusion_signal_agreement_and_recommendation():
    res = fusion_analyzer.calculate_fusion_signal(70, 60)

    assert res['agreement'] == 1
    assert res['confidence'] == 0.8
    assert res['recommendation'] == 'STRONG_BUY'
    assert res['fusion_score'] > 70


def test_calculate_fusion_signal_disagreement_dampens_score():
    res = fusion_analyzer.calculate_fusion_signal(80, -40)

    assert res['agreement'] == 0
    assert res['confidence'] == 0.4
    assert res['recommendation'] == 'HOLD'


def test_save_fusion_signal(tmp_path):
    dbp = str(tmp_path / 'q.db')
    db_core.init_db(dbp)
    signal = fusion_analyzer.calculate_fusion_signal(50, 40)
    with db_core.get_connection(dbp) as conn:
        fusion_analyzer.save_fusion_signal(
            conn, '000001', '2024-01-02', 50, 40, signal, regime='bull')
        row = conn.execute(
            "SELECT recommendation, regime FROM fusion_signals WHERE stock_code='000001'"
        ).fetchone()

    assert row['recommendation'] == signal['recommendation']
    assert row['regime'] == 'bull'
