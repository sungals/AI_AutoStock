"""표시용 한글 라벨 + 대시보드 한글 렌더 검증."""
import db_core
import auth
import labels
import web_app


def test_strategy_ko_mapping():
    assert labels.strategy_ko('momentum') == '모멘텀'
    assert labels.strategy_ko('value') == '가치주'
    assert labels.strategy_ko('turnaround') == '실적 전환주'
    assert labels.strategy_ko('quality_lowvol') == '퀄리티·저변동'
    assert labels.strategy_ko('all') == '전체'
    assert labels.strategy_ko('') == '-'
    assert labels.strategy_ko('unknown') == 'unknown'   # 미등록은 원본 유지(안전)


def test_recommendation_ko_mapping():
    assert labels.recommendation_ko('STRONG_BUY') == '적극 매수'
    assert labels.recommendation_ko('HOLD') == '보유'
    assert labels.recommendation_ko(None) == '-'


def test_dashboard_strategy_distribution_renders_korean(tmp_path):
    dbp = str(tmp_path / 'q.db')
    db_core.init_db(dbp)
    with db_core.get_connection(dbp) as conn:
        auth.create_user(conn, 'admin', 'secret')
        conn.execute("INSERT INTO companies (corp_code, stock_code, corp_name, market) "
                     "VALUES ('C005930','005930','삼성전자','KOSPI')")
        for strat in ('momentum', 'value', 'turnaround'):
            conn.execute(
                """INSERT INTO screening_results
                   (corp_code, stock_code, strategy, score, signals, screen_date)
                   VALUES ('C005930','005930',?,80,'[]','2026-06-19')""", (strat,))

    app = web_app.create_app(db_path=dbp, testing=True, auth_required=True)
    client = app.test_client()
    client.post('/login', data={'username': 'admin', 'password': 'secret'})
    body = client.get('/').data.decode('utf-8')

    # 전략 분포가 한글 라벨로 표시되고, 링크 파라미터는 영문 키 유지
    assert '모멘텀' in body and '가치주' in body and '실적 전환주' in body
    assert 'strategy=momentum' in body            # 링크는 영문 키 그대로


def test_screening_and_fusion_pages_render_korean(tmp_path):
    dbp = str(tmp_path / 'q.db')
    db_core.init_db(dbp)
    with db_core.get_connection(dbp) as conn:
        auth.create_user(conn, 'admin', 'secret')
        conn.execute("INSERT INTO companies (corp_code, stock_code, corp_name) "
                     "VALUES ('C005930','005930','삼성전자')")
        conn.execute(
            """INSERT INTO screening_results
               (corp_code, stock_code, strategy, score, signals, screen_date)
               VALUES ('C005930','005930','value',80,'[]','2026-06-19')""")
        conn.execute(
            """INSERT INTO fusion_signals
               (stock_code, calc_date, fusion_score, tech_score, emp_score,
                recommendation, regime)
               VALUES ('005930','2026-06-19',75,40,35,'STRONG_BUY','bull')""")

    app = web_app.create_app(db_path=dbp, testing=True, auth_required=True)
    client = app.test_client()
    client.post('/login', data={'username': 'admin', 'password': 'secret'})

    s = client.get('/screening?strategy=value').data.decode('utf-8')
    assert '가치주' in s and 'value="value"' in s        # 표시 한글, 옵션 값은 영문 키

    f = client.get('/fusion').data.decode('utf-8')
    assert '적극 매수' in f                                # STRONG_BUY → 한글
