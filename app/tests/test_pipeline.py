"""EOD 파이프라인 + 스크리닝 통합 테스트."""
import db_core
import screening
import run_daily_pipeline as pipe


# ── 스크리닝 ──

def test_screening_writes_results(fundamentals_db):
    dbp, dates = fundamentals_db
    with db_core.get_connection(dbp) as conn:
        counts = screening.run_all_screens(conn, '2022-03-01')
    assert counts['value'] >= 2          # 000001, 000002 저평가 우량
    assert counts['turnaround'] >= 1     # 000004 흑자전환
    with db_core.get_connection(dbp) as conn:
        rows = conn.execute(
            "SELECT stock_code FROM screening_results WHERE strategy='value'").fetchall()
    picked = {r['stock_code'] for r in rows}
    assert '000001' in picked and '000003' not in picked


def test_screening_rerun_replaces_same_date_results(fundamentals_db):
    dbp, dates = fundamentals_db
    with db_core.get_connection(dbp) as conn:
        first = screening.run_all_screens(conn, '2022-03-01')
        conn.execute(
            """INSERT INTO screening_results
               (corp_code, stock_code, strategy, score, signals, screen_date)
               VALUES ('XOLD', '000001', 'momentum', 99, '[]', '2022-03-01')""")
        second = screening.run_all_screens(conn, '2022-03-01')

    with db_core.get_connection(dbp) as conn:
        stale = conn.execute(
            "SELECT COUNT(*) c FROM screening_results "
            "WHERE screen_date='2022-03-01' AND corp_code='XOLD'"
        ).fetchone()['c']
        total = conn.execute(
            "SELECT COUNT(*) c FROM screening_results WHERE screen_date='2022-03-01'"
        ).fetchone()['c']

    assert first == second
    assert stale == 0
    assert total == sum(second.values())


def test_screening_uses_technical_signals_for_trend_and_mean_revert(tmp_path):
    dbp = str(tmp_path / 'q.db')
    db_core.init_db(dbp)
    with db_core.get_connection(dbp) as conn:
        for code in ('000001', '000002'):
            conn.execute(
                "INSERT INTO companies (corp_code, stock_code, corp_name) VALUES (?,?,?)",
                ('C' + code, code, 'CO' + code))
            for i in range(25):
                px = 1000 + i
                conn.execute(
                    """INSERT INTO price_data
                       (stock_code, trade_date, open, high, low, close, volume)
                       VALUES (?,?,?,?,?,?,?)""",
                    (code, '2024-01-%02d' % (i + 1), px, px + 10, px - 10, px, 10000))
        # 000001: 추세 추종 후보
        conn.execute(
            """INSERT INTO technical_signals
               (stock_code, calc_date, signal_name, signal_value, signal_label)
               VALUES ('000001', '2024-01-25', 'ma_cross', 1, '골든크로스')""")
        conn.execute(
            """INSERT INTO technical_signals
               (stock_code, calc_date, signal_name, signal_value, signal_label)
               VALUES ('000001', '2024-01-25', 'macd', 2, 'MACD 골든크로스')""")
        # 000002: 평균회귀 후보
        conn.execute(
            """INSERT INTO technical_signals
               (stock_code, calc_date, signal_name, signal_value, signal_label)
               VALUES ('000002', '2024-01-25', 'rsi_14', 24, 'RSI 과매도 (24)')""")
        conn.execute(
            """INSERT INTO technical_signals
               (stock_code, calc_date, signal_name, signal_value, signal_label)
               VALUES ('000002', '2024-01-25', 'bollinger', 900, '볼린저 하단 이탈 (과매도)')""")
        counts = screening.run_all_screens(conn, '2024-01-25')

    with db_core.get_connection(dbp) as conn:
        rows = conn.execute(
            "SELECT stock_code, strategy FROM screening_results WHERE screen_date='2024-01-25'"
        ).fetchall()
    picked = {(r['stock_code'], r['strategy']) for r in rows}
    assert counts['trend'] == 1
    assert counts['mean_revert'] == 1
    assert ('000001', 'trend') in picked
    assert ('000002', 'mean_revert') in picked


def test_screening_uses_price_range_for_volatility(tmp_path):
    dbp = str(tmp_path / 'q.db')
    db_core.init_db(dbp)
    with db_core.get_connection(dbp) as conn:
        conn.execute(
            "INSERT INTO companies (corp_code, stock_code, corp_name) VALUES (?,?,?)",
            ('C1', '000001', 'CO1'))
        for i in range(25):
            high_low = 20 if i < 24 else 100
            close = 1000
            conn.execute(
                """INSERT INTO price_data
                   (stock_code, trade_date, open, high, low, close, volume)
                   VALUES (?,?,?,?,?,?,?)""",
                ('000001', '2024-01-%02d' % (i + 1), close, close + high_low,
                 close - high_low, close, 10000))
        counts = screening.run_all_screens(conn, '2024-01-25')

    assert counts['volatility'] == 1


def test_screening_remaining_strategies(tmp_path):
    dbp = str(tmp_path / 'q.db')
    db_core.init_db(dbp)
    with db_core.get_connection(dbp) as conn:
        for code, sector in [('000001', '반도체'), ('000002', '반도체'), ('000003', '바이오')]:
            conn.execute(
                "INSERT INTO companies (corp_code, stock_code, corp_name, sector) VALUES (?,?,?,?)",
                ('C' + code, code, 'CO' + code, sector))
            for i in range(25):
                close = 1000 + i * (20 if code in ('000001', '000002') else 1)
                conn.execute(
                    """INSERT INTO price_data
                       (stock_code, trade_date, open, high, low, close, volume, value)
                       VALUES (?,?,?,?,?,?,?,?)""",
                    (code, '2024-01-%02d' % (i + 1), close, close + 5, close - 5,
                     close, 10000, close * 10000))
        # event
        conn.execute(
            """INSERT INTO dart_disclosures
               (rcept_no, corp_code, stock_code, corp_name, report_nm, rcept_dt, disclosure_type)
               VALUES ('R1', 'C000001', '000001', 'CO1', '단일판매 공급계약', '20240124', 'positive')""")
        conn.execute(
            """INSERT INTO sentiment_scores
               (stock_code, score_date, news_pos, news_neg, news_neu, composite_score)
               VALUES ('000001', '2024-01-25', 2, 0, 0, 1.0)""")
        # flow
        for d in ('2024-01-23', '2024-01-24', '2024-01-25'):
            conn.execute(
                """INSERT INTO investor_trading
                   (stock_code, trade_date, inst_net_buy, foreign_net_buy, retail_net_buy)
                   VALUES ('000001', ?, 1000, 2000, -3000)""", (d,))
        # quality_lowvol + guru
        conn.execute(
            """INSERT INTO calculated_metrics
               (corp_code, stock_code, calc_date, metric_name, metric_value)
               VALUES ('C000001', '000001', '2024-01-25', 'guru_score', 75)""")
        for acc, amount in (
                ('ifrs-full_ProfitLoss', 1_000_000_000),
                ('ifrs-full_Equity', 5_000_000_000),
                ('ifrs-full_Liabilities', 2_000_000_000)):
            conn.execute(
                """INSERT INTO financial_statements
                   (corp_code, bsns_year, reprt_code, fs_div, sj_div,
                    account_id, thstrm_amount, disclosed_at)
                   VALUES ('C000001', '2023', '11011', 'CFS', '', ?, ?, '2024-01-01')""",
                (acc, amount))
        counts = screening.run_all_screens(conn, '2024-01-25')

    with db_core.get_connection(dbp) as conn:
        rows = conn.execute(
            "SELECT strategy FROM screening_results WHERE stock_code='000001' AND screen_date='2024-01-25'"
        ).fetchall()
    strategies = {r['strategy'] for r in rows}
    assert counts['sector'] >= 2
    assert counts['event'] == 1
    assert counts['flow'] == 1
    assert counts['quality_lowvol'] >= 1
    assert counts['guru'] == 1
    assert {'event', 'flow', 'quality_lowvol', 'guru'} <= strategies


# ── 파이프라인 ──

def test_pipeline_runs_all_stages(seeded_db):
    dbp, dates = seeded_db
    summary = pipe.run_pipeline(dbp, do_collect=False, n_sim=6)
    statuses = dict(summary['stages'])
    # collect는 do_collect=False → skipped 메시지지만 completed로 기록(정상 종료)
    assert statuses['screening'] == 'completed'
    assert statuses['simulation'] == 'completed'
    assert statuses['optimize'] == 'completed'
    assert statuses['report'] == 'completed'
    # 산출물 확인
    with db_core.get_connection(dbp) as conn:
        assert conn.execute("SELECT COUNT(*) c FROM screening_results").fetchone()['c'] > 0
        assert conn.execute("SELECT COUNT(*) c FROM technical_signals").fetchone()['c'] > 0
        assert conn.execute("SELECT COUNT(*) c FROM fusion_signals").fetchone()['c'] > 0
        assert conn.execute("SELECT COUNT(*) c FROM simulation_runs").fetchone()['c'] > 0
        logs = conn.execute(
            "SELECT stage, status FROM pipeline_runs ORDER BY id").fetchall()
    stages_logged = [r['stage'] for r in logs]
    assert stages_logged == [
        'collect', 'market_cap', 'technical', 'news', 'macro', 'screening',
        'fusion', 'paper_trade', 'simulation', 'optimize', 'report']
    assert dict(summary['stages'])['market_cap'] == 'completed'
    assert dict(summary['stages'])['paper_trade'] == 'completed'   # 기본 skip
    assert summary['report'] is not None


def test_pipeline_paper_trade_stage_executes(fundamentals_db):
    dbp, dates = fundamentals_db
    summary = pipe.run_pipeline(dbp, do_collect=False, do_paper_trade=True,
                                trade_strategy='value', trade_top_n=5, n_sim=1)
    assert dict(summary['stages'])['paper_trade'] == 'completed'
    with db_core.get_connection(dbp) as conn:
        pf = conn.execute(
            "SELECT id FROM live_portfolios WHERE name='eod-paper'").fetchone()
        assert pf is not None                       # 모의 포트폴리오 생성됨
        trades = conn.execute(
            "SELECT COUNT(*) c FROM live_trades WHERE portfolio_id=?",
            (pf['id'],)).fetchone()['c']
    assert trades > 0                                # value 진입 매수 발생


def test_pipeline_dry_run_skips_everything(seeded_db):
    dbp, dates = seeded_db
    summary = pipe.run_pipeline(dbp, dry_run=True)
    assert all(status == 'skipped' for _, status in summary['stages'])
    with db_core.get_connection(dbp) as conn:
        assert conn.execute("SELECT COUNT(*) c FROM simulation_runs").fetchone()['c'] == 0
        logs = conn.execute("SELECT status FROM pipeline_runs").fetchall()
    assert all(r['status'] == 'skipped' for r in logs)


def test_pipeline_news_stage_skips_without_flag(seeded_db):
    dbp, dates = seeded_db
    summary = pipe.run_pipeline(dbp, do_collect=False, do_news=False, n_sim=1)
    assert dict(summary['stages'])['news'] == 'completed'
    with db_core.get_connection(dbp) as conn:
        msg = conn.execute(
            "SELECT message FROM pipeline_runs WHERE stage='news' ORDER BY id DESC LIMIT 1"
        ).fetchone()['message']
    assert 'do_news=False' in msg


def test_pipeline_stage_failure_isolated(seeded_db, monkeypatch):
    dbp, dates = seeded_db
    # simulation 단계를 강제 실패시켜도 이후 단계가 계속되는지
    import simulation_runner
    monkeypatch.setattr(simulation_runner, 'run_batch',
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError('boom')))
    summary = pipe.run_pipeline(dbp, do_collect=False, n_sim=6)
    statuses = dict(summary['stages'])
    assert statuses['simulation'] == 'failed'
    assert statuses['report'] == 'completed'     # 실패 격리 — 다음 단계 계속
    with db_core.get_connection(dbp) as conn:
        row = conn.execute(
            "SELECT message FROM pipeline_runs WHERE stage='simulation'").fetchone()
    assert 'boom' in (row['message'] or '')
