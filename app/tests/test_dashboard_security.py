"""대시보드 보안 하드닝 검증 — CSRF, 보안 헤더, SECRET_KEY."""
import os
import db_core
import auth
import web_app


# ── SECRET_KEY: 알려진 약한 기본값 금지 ──

def test_secret_key_uses_env_when_set(monkeypatch):
    monkeypatch.setenv('SECRET_KEY', 'env-provided-key')
    assert web_app._resolve_secret_key(testing=False) == 'env-provided-key'


def test_secret_key_random_when_missing_in_prod(monkeypatch):
    monkeypatch.delenv('SECRET_KEY', raising=False)
    k1 = web_app._resolve_secret_key(testing=False)
    k2 = web_app._resolve_secret_key(testing=False)
    assert k1 != 'dev-only-secret'        # 약한 기본값 아님
    assert len(k1) >= 32 and k1 != k2     # 무작위


def test_app_secret_key_not_weak_default(tmp_path, monkeypatch):
    monkeypatch.delenv('SECRET_KEY', raising=False)
    app = web_app.create_app(db_path=str(tmp_path / 'q.db'), testing=False)
    assert app.secret_key not in ('dev-only-secret', '', None)


# ── 보안 헤더 ──

def test_security_headers_present(tmp_path):
    app = web_app.create_app(db_path=str(tmp_path / 'q.db'), testing=True,
                             auth_required=False)
    res = app.test_client().get('/api/health')
    h = res.headers
    assert "default-src 'self'" in h['Content-Security-Policy']
    assert "frame-ancestors 'none'" in h['Content-Security-Policy']
    assert h['X-Content-Type-Options'] == 'nosniff'
    assert h['X-Frame-Options'] == 'DENY'
    assert h['Referrer-Policy'] == 'same-origin'


# ── CSRF: 운영 모드에서 토큰 없는 폼 POST 차단 ──

def test_csrf_blocks_tokenless_login_post_in_prod(tmp_path, monkeypatch):
    monkeypatch.setenv('SECRET_KEY', 'fixed-test-key')
    monkeypatch.setenv('FLASK_ENV', 'development')   # SECURE 쿠키 끔(테스트 편의)
    app = web_app.create_app(db_path=str(tmp_path / 'q.db'), testing=False,
                             auth_required=True)
    res = app.test_client().post('/login', data={'username': 'a', 'password': 'b'})
    assert res.status_code == 400        # CSRF 토큰 없음 → 거부


def test_login_form_renders_csrf_token_in_prod(tmp_path, monkeypatch):
    monkeypatch.setenv('SECRET_KEY', 'fixed-test-key')
    app = web_app.create_app(db_path=str(tmp_path / 'q.db'), testing=False,
                             auth_required=True)
    body = app.test_client().get('/login').data.decode('utf-8')
    assert 'name="csrf_token"' in body   # 폼에 토큰 주입됨


def test_json_auth_api_still_works_under_csrf(tmp_path, monkeypatch):
    """JSON 인증 API는 CSRF 면제 — 기존 동작 유지(운영 모드)."""
    monkeypatch.setenv('SECRET_KEY', 'fixed-test-key')
    monkeypatch.setenv('FLASK_ENV', 'development')
    dbp = str(tmp_path / 'q.db')
    db_core.init_db(dbp)
    with db_core.get_connection(dbp) as conn:
        auth.create_user(conn, 'admin', 'secret12')
    app = web_app.create_app(db_path=dbp, testing=False, auth_required=True)
    client = app.test_client()
    res = client.post('/api/auth/login', json={'username': 'admin', 'password': 'secret12'})
    assert res.status_code == 200        # CSRF 면제로 정상 동작
