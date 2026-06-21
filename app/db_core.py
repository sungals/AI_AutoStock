"""DB 코어 — 연결, 스키마 초기화, 멱등 마이그레이션.

04-DB-스키마.md의 서브셋(신뢰성 레이어가 사용하는 테이블)만 포함한다.
Connection Injection 패턴: 비즈니스 함수는 conn을 주입받는다.
Python 3.9 호환.
"""
from typing import Optional, List
from contextlib import contextmanager
import sqlite3
import config

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS companies (
    corp_code  TEXT PRIMARY KEY,
    stock_code TEXT NOT NULL UNIQUE,
    corp_name  TEXT NOT NULL,
    sector     TEXT,
    market     TEXT DEFAULT 'KOSPI',
    shares_outstanding INTEGER,
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS price_data (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    stock_code TEXT NOT NULL,
    trade_date TEXT NOT NULL,
    open       INTEGER, high INTEGER, low INTEGER, close INTEGER,
    volume     INTEGER, market_cap INTEGER,
    value      INTEGER,
    updated_at TEXT DEFAULT (datetime('now')),
    UNIQUE(stock_code, trade_date)
);
CREATE INDEX IF NOT EXISTS idx_price_stock_date ON price_data(stock_code, trade_date);

CREATE TABLE IF NOT EXISTS financial_statements (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    corp_code     TEXT NOT NULL,
    bsns_year     TEXT NOT NULL,
    reprt_code    TEXT NOT NULL,
    fs_div        TEXT NOT NULL,
    sj_div        TEXT NOT NULL DEFAULT '',
    account_id    TEXT NOT NULL,
    thstrm_amount INTEGER,
    updated_at    TEXT DEFAULT (datetime('now')),
    UNIQUE(corp_code, bsns_year, reprt_code, fs_div, sj_div, account_id)
);

CREATE TABLE IF NOT EXISTS calculated_metrics (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    corp_code    TEXT NOT NULL,
    stock_code   TEXT NOT NULL,
    calc_date    TEXT NOT NULL,
    metric_name  TEXT NOT NULL,
    metric_value REAL,
    UNIQUE(corp_code, calc_date, metric_name)
);

CREATE TABLE IF NOT EXISTS screening_results (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    corp_code   TEXT NOT NULL,
    stock_code  TEXT NOT NULL,
    strategy    TEXT NOT NULL,
    score       REAL NOT NULL DEFAULT 0,
    signals     TEXT,
    screen_date TEXT NOT NULL,
    UNIQUE(corp_code, strategy, screen_date)
);
CREATE INDEX IF NOT EXISTS idx_screening_date ON screening_results(screen_date, strategy);

CREATE TABLE IF NOT EXISTS news_articles (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    stock_code      TEXT NOT NULL,
    title           TEXT NOT NULL,
    url             TEXT,
    published_at    TEXT,
    source          TEXT,
    summary         TEXT,
    sentiment       TEXT,
    sentiment_score REAL,
    fetched_at      TEXT DEFAULT (datetime('now')),
    UNIQUE(stock_code, url)
);
CREATE INDEX IF NOT EXISTS idx_news_stock ON news_articles(stock_code, published_at);

CREATE TABLE IF NOT EXISTS stock_discussions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    stock_code      TEXT NOT NULL,
    title           TEXT NOT NULL,
    views           INTEGER DEFAULT 0,
    likes           INTEGER DEFAULT 0,
    published_at    TEXT,
    sentiment       TEXT,
    sentiment_score REAL,
    fetched_at      TEXT DEFAULT (datetime('now')),
    UNIQUE(stock_code, title, published_at)
);
CREATE INDEX IF NOT EXISTS idx_disc_stock ON stock_discussions(stock_code, published_at);

CREATE TABLE IF NOT EXISTS sentiment_scores (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    stock_code      TEXT NOT NULL,
    score_date      TEXT NOT NULL,
    news_pos        INTEGER DEFAULT 0,
    news_neg        INTEGER DEFAULT 0,
    news_neu        INTEGER DEFAULT 0,
    disc_pos        INTEGER DEFAULT 0,
    disc_neg        INTEGER DEFAULT 0,
    disc_neu        INTEGER DEFAULT 0,
    composite_score REAL,
    updated_at      TEXT DEFAULT (datetime('now')),
    UNIQUE(stock_code, score_date)
);
CREATE INDEX IF NOT EXISTS idx_sentiment_stock ON sentiment_scores(stock_code, score_date);

CREATE TABLE IF NOT EXISTS macro_prices (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol      TEXT NOT NULL,
    name_ko     TEXT,
    category    TEXT,
    trade_date  TEXT NOT NULL,
    close       REAL,
    change_pct  REAL,
    updated_at  TEXT DEFAULT (datetime('now')),
    UNIQUE(symbol, trade_date)
);
CREATE INDEX IF NOT EXISTS idx_macro_symbol ON macro_prices(symbol, trade_date);

CREATE TABLE IF NOT EXISTS investor_trading (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    stock_code      TEXT NOT NULL,
    trade_date      TEXT NOT NULL,
    inst_net_buy    INTEGER,
    foreign_net_buy INTEGER,
    retail_net_buy  INTEGER,
    updated_at      TEXT DEFAULT (datetime('now')),
    UNIQUE(stock_code, trade_date)
);
CREATE INDEX IF NOT EXISTS idx_investor_stock ON investor_trading(stock_code, trade_date);

CREATE TABLE IF NOT EXISTS dart_disclosures (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    rcept_no         TEXT NOT NULL UNIQUE,
    corp_code        TEXT NOT NULL,
    stock_code       TEXT NOT NULL,
    corp_name        TEXT,
    report_nm        TEXT,
    rcept_dt         TEXT,
    disclosure_type  TEXT,
    updated_at       TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_disclosure_stock ON dart_disclosures(stock_code, rcept_dt);

CREATE TABLE IF NOT EXISTS fusion_signals (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    stock_code     TEXT NOT NULL,
    calc_date      TEXT NOT NULL,
    tech_score     REAL,
    emp_score      REAL,
    fusion_score   REAL,
    confidence     REAL,
    agreement      INTEGER,
    recommendation TEXT,
    regime         TEXT,
    updated_at     TEXT DEFAULT (datetime('now')),
    UNIQUE(stock_code, calc_date)
);
CREATE INDEX IF NOT EXISTS idx_fusion_date ON fusion_signals(calc_date, fusion_score);

CREATE TABLE IF NOT EXISTS virtual_portfolios (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER,
    name            TEXT NOT NULL UNIQUE,
    strategy        TEXT NOT NULL,
    risk_profile    TEXT,
    portfolio_type  TEXT DEFAULT 'manual',
    horizon         TEXT,
    initial_capital REAL NOT NULL DEFAULT 10000000,
    cash            REAL NOT NULL DEFAULT 10000000,
    target_exit_date TEXT,
    created_at      TEXT DEFAULT (datetime('now')),
    updated_at      TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS virtual_trades (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    portfolio_id INTEGER NOT NULL REFERENCES virtual_portfolios(id),
    stock_code   TEXT NOT NULL,
    trade_date   TEXT NOT NULL,
    trade_type   TEXT NOT NULL,
    quantity     INTEGER NOT NULL,
    price        REAL NOT NULL,
    amount       REAL NOT NULL,
    reason       TEXT,
    exit_reason  TEXT,
    created_at   TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS virtual_performance (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    portfolio_id    INTEGER NOT NULL REFERENCES virtual_portfolios(id),
    perf_date       TEXT NOT NULL,
    portfolio_value REAL NOT NULL,
    daily_return    REAL,
    total_return    REAL,
    mdd             REAL,
    sharpe          REAL,
    realized_pnl    REAL,
    updated_at      TEXT DEFAULT (datetime('now')),
    UNIQUE(portfolio_id, perf_date)
);

CREATE TABLE IF NOT EXISTS live_portfolios (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id           INTEGER,
    name              TEXT NOT NULL UNIQUE,
    mode              TEXT NOT NULL DEFAULT 'mock',
    initial_capital   REAL NOT NULL,
    cash              REAL NOT NULL,
    strategy          TEXT,
    max_invest_ratio  REAL DEFAULT 0.9,
    daily_loss_limit  REAL DEFAULT 0.03,
    max_position_size REAL DEFAULT 0.2,
    sizing_mode       TEXT DEFAULT 'equal',
    created_at        TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS live_trades (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    portfolio_id INTEGER NOT NULL REFERENCES live_portfolios(id),
    stock_code   TEXT NOT NULL,
    trade_date   TEXT NOT NULL,
    trade_type   TEXT NOT NULL,
    quantity     INTEGER NOT NULL,
    price        REAL NOT NULL,
    amount       REAL NOT NULL,
    exit_reason  TEXT,
    order_id     TEXT,
    metadata     TEXT DEFAULT '{}',
    created_at   TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_live_trades ON live_trades(portfolio_id, trade_date);

CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    is_admin      INTEGER NOT NULL DEFAULT 0,
    created_at    TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS technical_signals (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    stock_code   TEXT NOT NULL,
    calc_date    TEXT NOT NULL,
    signal_name  TEXT NOT NULL,
    signal_value REAL,
    signal_label TEXT,
    updated_at   TEXT DEFAULT (datetime('now')),
    UNIQUE(stock_code, calc_date, signal_name)
);
CREATE INDEX IF NOT EXISTS idx_tech_stock_date ON technical_signals(stock_code, calc_date);

CREATE TABLE IF NOT EXISTS simulation_runs (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id            TEXT,
    strategy            TEXT NOT NULL,
    risk_profile        TEXT NOT NULL,
    window_months       INTEGER,
    start_offset_months INTEGER,
    cagr   REAL, mdd REAL, sharpe REAL, alpha REAL,
    n_trades INTEGER,
    market_regime TEXT,
    status   TEXT DEFAULT 'ok',
    error_msg TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_sim_runs_batch ON simulation_runs(batch_id);

CREATE TABLE IF NOT EXISTS backtest_runs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    strategy        TEXT NOT NULL,
    start_date      TEXT NOT NULL,
    end_date        TEXT NOT NULL,
    top_n           INTEGER NOT NULL DEFAULT 5,
    rebalance       TEXT NOT NULL DEFAULT 'monthly',
    initial_capital REAL NOT NULL DEFAULT 10000000,
    commission_rate REAL NOT NULL DEFAULT 0,
    created_at      TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS backtest_metrics (
    run_id       INTEGER NOT NULL,
    metric_name  TEXT NOT NULL,
    metric_value REAL,
    PRIMARY KEY (run_id, metric_name)
);

CREATE TABLE IF NOT EXISTS algo_params (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    param_name  TEXT NOT NULL,
    param_value REAL NOT NULL,
    regime      TEXT,
    source      TEXT DEFAULT 'optimizer',
    created_at  TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS pipeline_runs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    run_date    TEXT NOT NULL,
    stage       TEXT NOT NULL,
    status      TEXT NOT NULL,           -- 'running' | 'completed' | 'failed' | 'skipped'
    message     TEXT,
    started_at  TEXT DEFAULT (datetime('now')),
    finished_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_pipeline_run ON pipeline_runs(run_date, stage);
"""


@contextmanager
def get_connection(db_path: Optional[str] = None):
    """SQLite 연결 컨텍스트 매니저. 커밋/롤백/클로즈 자동 처리."""
    path = db_path or config.DB_PATH
    conn = sqlite3.connect(path, timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _table_cols(conn, table: str) -> List[str]:
    return [r[1] for r in conn.execute("PRAGMA table_info(%s)" % table).fetchall()]


def _migrate_add_reliability_columns(conn) -> None:
    """백테스트 신뢰성 레이어 컬럼 추가 (멱등)."""
    if 'disclosed_at' not in _table_cols(conn, 'financial_statements'):
        conn.execute("ALTER TABLE financial_statements ADD COLUMN disclosed_at TEXT")

    # 발행주식수 캐시 (시총 계산용; DART 재호출 최소화)
    if 'shares_outstanding' not in _table_cols(conn, 'companies'):
        conn.execute("ALTER TABLE companies ADD COLUMN shares_outstanding INTEGER")

    sim_cols = [
        ('is_cagr', 'REAL'), ('oos_cagr', 'REAL'), ('deflated_sharpe', 'REAL'),
        ('cost_bps', 'REAL'), ('gate_passed', 'INTEGER DEFAULT 0'), ('gate_reason', 'TEXT'),
    ]
    existing = _table_cols(conn, 'simulation_runs')
    for col, ddl in sim_cols:
        if col not in existing:
            conn.execute("ALTER TABLE simulation_runs ADD COLUMN %s %s" % (col, ddl))

    bt_cols = [
        ('slippage_bps', 'REAL DEFAULT 0'), ('tax_rate', 'REAL DEFAULT 0'),
        ('fill_model', "TEXT DEFAULT 'realistic'"),
    ]
    existing = _table_cols(conn, 'backtest_runs')
    for col, ddl in bt_cols:
        if col not in existing:
            conn.execute("ALTER TABLE backtest_runs ADD COLUMN %s %s" % (col, ddl))


def init_db(db_path: Optional[str] = None) -> None:
    """스키마 생성 + 마이그레이션 (멱등). 매 시작 시 호출해도 안전."""
    with get_connection(db_path) as conn:
        conn.executescript(SCHEMA_SQL)
        _migrate_add_reliability_columns(conn)
