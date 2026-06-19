"""최소 Flask REST API.

05-구현-가이드 Phase 10의 조회 API/SSE 패턴을 현재 단독 앱 구조에 맞춰 구현한다.
"""
from datetime import date
import json
import os
import time
from functools import wraps

from flask import Flask, Response, jsonify, redirect, render_template, request, session, stream_with_context, url_for

import auth
import dashboard_data
import db_core
import config
import watchlist


def _limit_arg(default: int = 50, cap: int = 200) -> int:
    try:
        return min(max(int(request.args.get('limit', default)), 1), cap)
    except ValueError:
        return default


def _rowdicts(rows):
    return [dict(r) for r in rows]


_RATE_BUCKETS = {}


def _normalize_base_path(value):
    path = (value or '').strip()
    if not path or path == '/':
        return ''
    if not path.startswith('/'):
        path = '/' + path
    return path.rstrip('/')


def _join_base_path(base_path, path):
    base = _normalize_base_path(base_path)
    target = path if path.startswith('/') else '/' + path
    if not base:
        return target
    return base + target


def create_app(db_path=None, testing: bool = False, auth_required=None,
               rate_limit_count: int = 120, rate_limit_window: int = 60,
               base_path=None) -> Flask:
    app = Flask(__name__, template_folder='templates')
    app.config['DB_PATH'] = db_path
    app.config['TESTING'] = testing
    app.config['AUTH_REQUIRED'] = (not testing) if auth_required is None else auth_required
    app.config['RATE_LIMIT_COUNT'] = rate_limit_count
    app.config['RATE_LIMIT_WINDOW'] = rate_limit_window
    app.config['BASE_PATH'] = _normalize_base_path(base_path if base_path is not None else config.BASE_PATH)
    app.secret_key = os.environ.get('SECRET_KEY', 'dev-only-secret')
    app.config['SESSION_COOKIE_HTTPONLY'] = True
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
    app.config['SESSION_COOKIE_SECURE'] = not testing and os.environ.get('FLASK_ENV') != 'development'
    db_core.init_db(db_path)
    _RATE_BUCKETS.clear()

    def app_path(path='/'):
        return _join_base_path(app.config['BASE_PATH'], path)

    def current_user():
        uid = session.get('user_id')
        if not uid:
            return None
        with db_core.get_connection(app.config['DB_PATH']) as conn:
            return auth.get_user(conn, int(uid))

    def require_auth(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if app.config['AUTH_REQUIRED'] and current_user() is None:
                return jsonify({'error': 'unauthorized'}), 401
            return fn(*args, **kwargs)
        return wrapper

    def require_page_auth(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if app.config['AUTH_REQUIRED'] and current_user() is None:
                return redirect(app_path('/login'))
            return fn(*args, **kwargs)
        return wrapper

    @app.context_processor
    def inject_helpers():
        return {
            'app_path': app_path,
            'static_path': lambda filename: app_path('/static/' + filename.lstrip('/')),
            'base_path': app.config['BASE_PATH'],
        }

    @app.before_request
    def rate_limit():
        count = app.config['RATE_LIMIT_COUNT']
        window = app.config['RATE_LIMIT_WINDOW']
        if count <= 0 or window <= 0:
            return None
        now = time.time()
        key = (request.remote_addr or 'local', request.path)
        bucket = [t for t in _RATE_BUCKETS.get(key, []) if now - t < window]
        if len(bucket) >= count:
            _RATE_BUCKETS[key] = bucket
            return jsonify({'error': 'rate_limited'}), 429
        bucket.append(now)
        _RATE_BUCKETS[key] = bucket
        return None

    @app.get('/api/health')
    def health():
        return jsonify({'ok': True})

    @app.get('/login')
    def login_page():
        if current_user() is not None:
            return redirect(app_path('/'))
        return render_template('login.html', error='')

    @app.post('/login')
    def login_form():
        username = request.form.get('username', '')
        password = request.form.get('password', '')
        with db_core.get_connection(app.config['DB_PATH']) as conn:
            user = auth.verify_user(conn, username, password)
        if not user:
            return render_template('login.html', error='로그인 실패'), 401
        session.clear()
        session['user_id'] = user['id']
        return redirect(app_path('/'))

    @app.post('/logout')
    def logout_form():
        session.clear()
        return redirect(app_path('/login'))

    @app.get('/')
    @require_page_auth
    def dashboard():
        selected_market = request.args.get('market', 'ALL').upper()
        if selected_market not in watchlist.market_options():
            selected_market = 'ALL'
        selected_sort = request.args.get('sort', 'market').lower()
        if selected_sort not in ('market', 'fusion', 'screening', 'change'):
            selected_sort = 'market'
        with db_core.get_connection(app.config['DB_PATH']) as conn:
            screen_date = conn.execute(
                "SELECT MAX(screen_date) AS d FROM screening_results").fetchone()['d']
            screening_count = conn.execute(
                "SELECT COUNT(*) AS c FROM screening_results WHERE screen_date=?",
                (screen_date,)).fetchone()['c'] if screen_date else 0
            fusion_date = conn.execute(
                "SELECT MAX(calc_date) AS d FROM fusion_signals").fetchone()['d']
            fusion_count = conn.execute(
                "SELECT COUNT(*) AS c FROM fusion_signals WHERE calc_date=?",
                (fusion_date,)).fetchone()['c'] if fusion_date else 0
            steps = conn.execute(
                """SELECT stage, status, message FROM pipeline_runs
                   ORDER BY id DESC LIMIT 8""").fetchall()
            strategy_rows = conn.execute(
                """SELECT strategy, COUNT(*) AS c
                   FROM screening_results
                   WHERE screen_date=?
                   GROUP BY strategy
                   ORDER BY c DESC, strategy""",
                (screen_date,)).fetchall() if screen_date else []
            fusion_rows = conn.execute(
                """SELECT stock_code, fusion_score, recommendation
                   FROM fusion_signals
                   WHERE calc_date=?
                   ORDER BY fusion_score DESC
                   LIMIT 6""",
                (fusion_date,)).fetchall() if fusion_date else []
            macro_rows = conn.execute(
                """SELECT symbol, close, change_pct
                   FROM macro_prices
                   WHERE trade_date=(SELECT MAX(trade_date) FROM macro_prices)
                   ORDER BY symbol""").fetchall()
            rep_rows = {}
            for market in ('KOSPI', 'KOSDAQ'):
                if selected_market != 'ALL' and selected_market != market:
                    continue
                rows = dashboard_data.get_representative_overviews(
                    conn, watchlist.REPRESENTATIVE_STOCKS.get(market, []))
                if selected_sort == 'fusion':
                    rows.sort(key=lambda r: (r['fusion_score'] is not None, r['fusion_score'] or -9999), reverse=True)
                elif selected_sort == 'screening':
                    rows.sort(key=lambda r: (r['screen_score'] is not None, r['screen_score'] or -9999), reverse=True)
                elif selected_sort == 'change':
                    rows.sort(key=lambda r: (r['change_pct'] is not None, r['change_pct'] or -9999), reverse=True)
                rep_rows[market] = rows
        max_strategy = max([r['c'] for r in strategy_rows], default=1)
        strategy_counts = [
            {'strategy': r['strategy'], 'count': r['c'],
             'width': int(r['c'] / max_strategy * 100)}
            for r in strategy_rows
        ]
        max_fusion = max([abs(r['fusion_score'] or 0) for r in fusion_rows], default=1)
        fusion_top = [
            {'stock_code': r['stock_code'], 'fusion_score': r['fusion_score'] or 0,
             'recommendation': r['recommendation'],
             'width': int(abs(r['fusion_score'] or 0) / max_fusion * 100)}
            for r in fusion_rows
        ]
        return render_template(
            'dashboard.html', user=current_user(), screen_date=screen_date,
            screening_count=screening_count, fusion_date=fusion_date,
            fusion_count=fusion_count, steps=_rowdicts(steps),
            strategy_counts=strategy_counts, fusion_top=fusion_top,
            macro_rows=_rowdicts(macro_rows),
            selected_market=selected_market, selected_sort=selected_sort,
            market_options=watchlist.market_options(),
            rep_rows=rep_rows)

    @app.get('/screening')
    @require_page_auth
    def screening_page():
        strategy = request.args.get('strategy', 'all')
        with db_core.get_connection(app.config['DB_PATH']) as conn:
            row = conn.execute("SELECT MAX(screen_date) AS d FROM screening_results").fetchone()
            screen_date = row['d'] if row else None
            if not screen_date:
                rows = []
            elif strategy == 'all':
                rows = conn.execute(
                    """SELECT sr.*, c.corp_name, c.sector FROM screening_results sr
                       LEFT JOIN companies c ON c.corp_code=sr.corp_code
                       WHERE sr.screen_date=? ORDER BY sr.score DESC LIMIT 100""",
                    (screen_date,)).fetchall()
            else:
                rows = conn.execute(
                    """SELECT sr.*, c.corp_name, c.sector FROM screening_results sr
                       LEFT JOIN companies c ON c.corp_code=sr.corp_code
                       WHERE sr.screen_date=? AND sr.strategy=?
                       ORDER BY sr.score DESC LIMIT 100""",
                    (screen_date, strategy)).fetchall()
        return render_template(
            'screening.html', strategy=strategy, screen_date=screen_date,
            rows=_rowdicts(rows))

    @app.get('/fusion')
    @require_page_auth
    def fusion_page():
        with db_core.get_connection(app.config['DB_PATH']) as conn:
            row = conn.execute("SELECT MAX(calc_date) AS d FROM fusion_signals").fetchone()
            calc_date = row['d'] if row else None
            rows = conn.execute(
                """SELECT fs.*, c.corp_name, c.sector FROM fusion_signals fs
                   LEFT JOIN companies c ON c.stock_code=fs.stock_code
                   WHERE fs.calc_date=? ORDER BY fs.fusion_score DESC LIMIT 100""",
                (calc_date,)).fetchall() if calc_date else []
        return render_template('fusion.html', calc_date=calc_date, rows=_rowdicts(rows))

    @app.get('/pipeline')
    @require_page_auth
    def pipeline_page():
        run_date = request.args.get('date') or date.today().isoformat()
        with db_core.get_connection(app.config['DB_PATH']) as conn:
            rows = conn.execute(
                """SELECT stage, status, message, started_at, finished_at
                   FROM pipeline_runs WHERE run_date=? ORDER BY id""",
                (run_date,)).fetchall()
        return render_template('pipeline.html', run_date=run_date, rows=_rowdicts(rows))

    @app.post('/api/auth/login')
    def login():
        payload = request.get_json(silent=True) or {}
        username = payload.get('username', '')
        password = payload.get('password', '')
        with db_core.get_connection(app.config['DB_PATH']) as conn:
            user = auth.verify_user(conn, username, password)
        if not user:
            return jsonify({'error': 'invalid_credentials'}), 401
        session.clear()
        session['user_id'] = user['id']
        return jsonify({'user': user})

    @app.post('/api/auth/logout')
    def logout():
        session.clear()
        return jsonify({'ok': True})

    @app.post('/api/auth/change-password')
    @require_auth
    def change_password():
        user = current_user()
        payload = request.get_json(silent=True) or {}
        current_password = payload.get('current_password', '')
        new_password = payload.get('new_password', '')
        if len(new_password) < 8:
            return jsonify({'error': 'new_password_too_short'}), 400
        with db_core.get_connection(app.config['DB_PATH']) as conn:
            changed = auth.change_password(
                conn, user['username'], current_password, new_password)
        if not changed:
            return jsonify({'error': 'invalid_current_password'}), 401
        session.clear()
        return jsonify({'ok': True})

    @app.get('/api/auth/me')
    @require_auth
    def me():
        return jsonify({'user': current_user()})

    @app.get('/api/screening/results')
    @require_auth
    def get_screening_results():
        strategy = request.args.get('strategy', 'all')
        screen_date = request.args.get('date')
        limit = _limit_arg()
        with db_core.get_connection(app.config['DB_PATH']) as conn:
            if screen_date is None:
                if strategy == 'all':
                    row = conn.execute(
                        "SELECT MAX(screen_date) AS d FROM screening_results").fetchone()
                else:
                    row = conn.execute(
                        "SELECT MAX(screen_date) AS d FROM screening_results WHERE strategy=?",
                        (strategy,)).fetchone()
                screen_date = row['d'] if row else None
            if not screen_date:
                return jsonify({'results': [], 'count': 0, 'screen_date': None})

            if strategy == 'all':
                rows = conn.execute(
                    """SELECT sr.*, c.corp_name, c.sector
                       FROM screening_results sr
                       LEFT JOIN companies c ON c.corp_code = sr.corp_code
                       WHERE sr.screen_date = ?
                       ORDER BY sr.score DESC
                       LIMIT ?""",
                    (screen_date, limit)).fetchall()
            else:
                rows = conn.execute(
                    """SELECT sr.*, c.corp_name, c.sector
                       FROM screening_results sr
                       LEFT JOIN companies c ON c.corp_code = sr.corp_code
                       WHERE sr.strategy = ? AND sr.screen_date = ?
                       ORDER BY sr.score DESC
                       LIMIT ?""",
                    (strategy, screen_date, limit)).fetchall()
        return jsonify({
            'results': _rowdicts(rows),
            'count': len(rows),
            'screen_date': screen_date,
        })

    @app.get('/api/fusion/signals')
    @require_auth
    def get_fusion_signals():
        calc_date = request.args.get('date')
        limit = _limit_arg()
        with db_core.get_connection(app.config['DB_PATH']) as conn:
            if calc_date is None:
                row = conn.execute("SELECT MAX(calc_date) AS d FROM fusion_signals").fetchone()
                calc_date = row['d'] if row else None
            if not calc_date:
                return jsonify({'results': [], 'count': 0, 'calc_date': None})
            rows = conn.execute(
                """SELECT fs.*, c.corp_name, c.sector
                   FROM fusion_signals fs
                   LEFT JOIN companies c ON c.stock_code = fs.stock_code
                   WHERE fs.calc_date = ?
                   ORDER BY fs.fusion_score DESC
                   LIMIT ?""",
                (calc_date, limit)).fetchall()
        return jsonify({'results': _rowdicts(rows), 'count': len(rows), 'calc_date': calc_date})

    @app.get('/api/pipeline/status')
    @require_auth
    def pipeline_status():
        run_date = request.args.get('date') or date.today().isoformat()
        with db_core.get_connection(app.config['DB_PATH']) as conn:
            rows = conn.execute(
                """SELECT stage, status, message, started_at, finished_at
                   FROM pipeline_runs
                   WHERE run_date = ?
                   ORDER BY id""",
                (run_date,)).fetchall()
        return jsonify({'run_date': run_date, 'steps': _rowdicts(rows)})

    @app.get('/api/pipeline/stream')
    @require_auth
    def pipeline_stream():
        run_date = request.args.get('date') or date.today().isoformat()

        def generate():
            with db_core.get_connection(app.config['DB_PATH']) as conn:
                rows = conn.execute(
                    """SELECT stage, status, message, started_at, finished_at
                       FROM pipeline_runs
                       WHERE run_date = ?
                       ORDER BY id""",
                    (run_date,)).fetchall()
            steps = _rowdicts(rows)
            done = bool(steps) and (any(s['status'] == 'failed' for s in steps) or
                                    steps[-1]['status'] in ('completed', 'skipped'))
            yield 'data: %s\n\n' % json.dumps(
                {'run_date': run_date, 'steps': steps, 'done': done},
                ensure_ascii=False)

        return Response(
            stream_with_context(generate()), mimetype='text/event-stream',
            headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})

    return app


app = create_app()


if __name__ == '__main__':
    app.run(host='127.0.0.1', port=int(os.environ.get('PORT', '5000')), debug=False)
