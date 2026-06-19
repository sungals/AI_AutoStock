"""Phase 10: 최소 REST API."""
import json

import db_core
import web_app


def test_screening_results_api(fundamentals_db, monkeypatch):
    dbp, dates = fundamentals_db
    import screening
    with db_core.get_connection(dbp) as conn:
        screening.run_all_screens(conn, '2022-03-01')

    app = web_app.create_app(db_path=dbp, testing=True)
    client = app.test_client()
    res = client.get('/api/screening/results?strategy=value&limit=5')
    data = res.get_json()

    assert res.status_code == 200
    assert data['count'] >= 1
    assert data['results'][0]['strategy'] == 'value'


def test_pipeline_status_api(tmp_path):
    dbp = str(tmp_path / 'q.db')
    db_core.init_db(dbp)
    import db_ops
    sid = db_ops.log_start(dbp, '2024-01-02', 'screening')
    db_ops.log_finish(dbp, sid, 'completed', 'ok')

    app = web_app.create_app(db_path=dbp, testing=True)
    res = app.test_client().get('/api/pipeline/status?date=2024-01-02')
    data = res.get_json()

    assert res.status_code == 200
    assert data['steps'][0]['stage'] == 'screening'
    assert data['steps'][0]['status'] == 'completed'


def test_pipeline_stream_api(tmp_path):
    dbp = str(tmp_path / 'q.db')
    db_core.init_db(dbp)
    import db_ops
    sid = db_ops.log_start(dbp, '2024-01-02', 'report')
    db_ops.log_finish(dbp, sid, 'completed', 'done')

    app = web_app.create_app(db_path=dbp, testing=True)
    res = app.test_client().get('/api/pipeline/stream?date=2024-01-02')
    payload = res.data.decode('utf-8')

    assert res.status_code == 200
    assert payload.startswith('data: ')
    assert json.loads(payload.split('data: ', 1)[1])['done'] is True


def test_dashboard_requires_login_and_renders_after_login(fundamentals_db):
    dbp, dates = fundamentals_db
    import auth
    import screening
    with db_core.get_connection(dbp) as conn:
        auth.create_user(conn, 'admin', 'secret')
        screening.run_all_screens(conn, '2022-03-01')

    app = web_app.create_app(db_path=dbp, testing=True, auth_required=True)
    client = app.test_client()

    assert client.get('/').status_code == 302
    assert client.post('/login', data={'username': 'admin', 'password': 'secret'}).status_code == 302
    res = client.get('/')
    body = res.data.decode('utf-8')

    assert res.status_code == 200
    assert 'TTAK Quant' in body
    assert '스크리닝' in body


def test_screening_page_renders_table(fundamentals_db):
    dbp, dates = fundamentals_db
    import auth
    import screening
    with db_core.get_connection(dbp) as conn:
        auth.create_user(conn, 'admin', 'secret')
        screening.run_all_screens(conn, '2022-03-01')

    app = web_app.create_app(db_path=dbp, testing=True, auth_required=True)
    client = app.test_client()
    client.post('/login', data={'username': 'admin', 'password': 'secret'})
    res = client.get('/screening?strategy=value')
    body = res.data.decode('utf-8')

    assert res.status_code == 200
    assert '<table' in body
    assert 'value' in body


def test_base_path_prefixes_ui_links(fundamentals_db):
    dbp, dates = fundamentals_db
    import auth
    with db_core.get_connection(dbp) as conn:
        auth.create_user(conn, 'admin', 'secret')

    app = web_app.create_app(
        db_path=dbp, testing=True, auth_required=True, base_path='/ttakquant')
    client = app.test_client()

    res = client.get('/')
    assert res.status_code == 302
    assert res.headers['Location'].endswith('/ttakquant/login')

    login = client.get('/login')
    body = login.data.decode('utf-8')
    assert '/ttakquant/static/app.css' in body
    assert 'action="/ttakquant/login"' in body
