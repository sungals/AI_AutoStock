"""Phase 10 보안: 사용자 인증과 API 보호."""
import db_core
import auth
import web_app


def test_create_and_verify_user(tmp_path):
    dbp = str(tmp_path / 'q.db')
    db_core.init_db(dbp)
    with db_core.get_connection(dbp) as conn:
        user_id = auth.create_user(conn, 'admin', 'secret', is_admin=True)
        user = auth.verify_user(conn, 'admin', 'secret')
        bad = auth.verify_user(conn, 'admin', 'wrong')

    assert user_id > 0
    assert user['username'] == 'admin'
    assert user['is_admin'] is True
    assert bad is None


def test_change_password_invalidates_old_password(tmp_path):
    dbp = str(tmp_path / 'q.db')
    db_core.init_db(dbp)
    with db_core.get_connection(dbp) as conn:
        auth.create_user(conn, 'admin', 'old-secret')
        changed = auth.change_password(conn, 'admin', 'old-secret', 'new-secret')
        old_user = auth.verify_user(conn, 'admin', 'old-secret')
        new_user = auth.verify_user(conn, 'admin', 'new-secret')

    assert changed is True
    assert old_user is None
    assert new_user['username'] == 'admin'


def test_change_password_rejects_wrong_current_password(tmp_path):
    dbp = str(tmp_path / 'q.db')
    db_core.init_db(dbp)
    with db_core.get_connection(dbp) as conn:
        auth.create_user(conn, 'admin', 'old-secret')
        changed = auth.change_password(conn, 'admin', 'wrong', 'new-secret')
        user = auth.verify_user(conn, 'admin', 'old-secret')

    assert changed is False
    assert user['username'] == 'admin'


def test_api_requires_login_when_auth_enabled(tmp_path):
    dbp = str(tmp_path / 'q.db')
    db_core.init_db(dbp)
    with db_core.get_connection(dbp) as conn:
        auth.create_user(conn, 'admin', 'secret')

    app = web_app.create_app(db_path=dbp, testing=True, auth_required=True)
    client = app.test_client()

    assert client.get('/api/screening/results').status_code == 401
    login = client.post('/api/auth/login', json={'username': 'admin', 'password': 'secret'})
    assert login.status_code == 200
    assert login.get_json()['user']['username'] == 'admin'
    assert client.get('/api/screening/results').status_code == 200
    assert client.post('/api/auth/logout').status_code == 200
    assert client.get('/api/screening/results').status_code == 401


def test_change_password_api_requires_login_and_updates_password(tmp_path):
    dbp = str(tmp_path / 'q.db')
    db_core.init_db(dbp)
    with db_core.get_connection(dbp) as conn:
        auth.create_user(conn, 'admin', 'old-secret')

    app = web_app.create_app(db_path=dbp, testing=True, auth_required=True)
    client = app.test_client()

    assert client.post('/api/auth/change-password', json={
        'current_password': 'old-secret', 'new_password': 'new-secret'
    }).status_code == 401

    assert client.post('/api/auth/login', json={
        'username': 'admin', 'password': 'old-secret'
    }).status_code == 200
    res = client.post('/api/auth/change-password', json={
        'current_password': 'old-secret', 'new_password': 'new-secret'
    })
    assert res.status_code == 200
    client.post('/api/auth/logout')

    assert client.post('/api/auth/login', json={
        'username': 'admin', 'password': 'old-secret'
    }).status_code == 401
    assert client.post('/api/auth/login', json={
        'username': 'admin', 'password': 'new-secret'
    }).status_code == 200


def test_rate_limit_returns_429(tmp_path):
    dbp = str(tmp_path / 'q.db')
    db_core.init_db(dbp)
    app = web_app.create_app(
        db_path=dbp, testing=True, auth_required=False,
        rate_limit_count=2, rate_limit_window=60)
    client = app.test_client()

    assert client.get('/api/health').status_code == 200
    assert client.get('/api/health').status_code == 200
    assert client.get('/api/health').status_code == 429
