"""EOD 파이프라인 — 장마감 후 수집→스크리닝→시뮬레이션→최적화→리포트 오케스트레이션.

03-시스템-아키텍처.md §6의 10단계를 구현된 모듈에 맞춰 5개 스테이지로 통합한다.
각 단계는 pipeline_runs에 기록되고, 단계 실패는 격리(가능한 한 다음 단계 계속)된다.
cron 진입점. Python 3.9 호환.

사용:
    python run_daily_pipeline.py [--db PATH] [--collect] [--dry-run] [--n-sim N]
"""
from typing import Dict, List, Optional, Tuple
from datetime import date

import db_core
import db_ops


# ── 스테이지 구현 ──

def _latest_trade_date(db_path: Optional[str]) -> Optional[str]:
    with db_core.get_connection(db_path) as conn:
        row = conn.execute("SELECT MAX(trade_date) AS d FROM price_data").fetchone()
    return row['d'] if row else None


def _price_window(db_path: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    with db_core.get_connection(db_path) as conn:
        row = conn.execute(
            "SELECT MIN(trade_date) AS a, MAX(trade_date) AS b FROM price_data").fetchone()
    return (row['a'], row['b']) if row else (None, None)


def _existing_stock_codes(db_path: Optional[str]) -> List[str]:
    with db_core.get_connection(db_path) as conn:
        return [r['stock_code'] for r in
                conn.execute("SELECT stock_code FROM companies").fetchall()]


def stage_collect(db_path: Optional[str], ctx: Dict) -> str:
    """종목 마스터 + 가격(pykrx) + 재무(DART) 수집.

    collect_opts 미지정 시 기본값(오늘자 수집)을 구성한다.
    이미 companies가 있으면 마스터 재구축을 건너뛰고 증분 수집한다.
    """
    if not ctx.get('do_collect'):
        return 'skipped (do_collect=False — 기존 데이터 사용)'
    import collectors

    today = date.today().strftime('%Y%m%d')
    year = date.today().year
    opts = dict(ctx.get('collect_opts') or {})
    opts.setdefault('markets', ('KOSPI', 'KOSDAQ'))
    opts.setdefault('start', today)
    opts.setdefault('end', today)
    opts.setdefault('years', [str(year - 1), str(year)])

    stock_codes = opts.get('stock_codes')
    existing = _existing_stock_codes(db_path)
    # 마스터가 있으면 재구축 생략(증분). 명시 종목이 없으면 기존 유니버스 사용.
    build_master = not existing and stock_codes is None
    if stock_codes is None and existing:
        stock_codes = existing

    summary = collectors.collect_all(
        db_path, markets=opts['markets'], start=opts['start'], end=opts['end'],
        years=opts['years'], stock_codes=stock_codes, build_master=build_master)
    fin = summary.get('financials', {})
    return 'master=%s prices=%s financials=%s' % (
        summary.get('companies'), summary.get('prices', {}).get('rows'),
        'skip' if fin.get('skipped') else fin.get('rows'))


def stage_screening(db_path: Optional[str], ctx: Dict) -> str:
    import screening
    screen_date = ctx.get('screen_date') or _latest_trade_date(db_path)
    if not screen_date:
        raise RuntimeError('가격 데이터 없음 — 스크리닝 불가')
    ctx['screen_date'] = screen_date
    with db_core.get_connection(db_path) as conn:
        counts = screening.run_all_screens(conn, screen_date)
    parts = ['%s=%d' % (k, counts[k]) for k in sorted(counts)]
    return 'date=%s %s' % (screen_date, ' '.join(parts))


def stage_market_cap(db_path: Optional[str], ctx: Dict) -> str:
    """DART 발행주식수로 price_data.market_cap 채움 (KRX 시총 차단 우회).

    주식수는 companies에 캐시되어, 매일 실행 시 새 가격행만 빠르게 갱신한다.
    DART 키 없으면 graceful skip(value/turnaround의 PER/PBR만 비게 됨).
    """
    import financial_collector
    with db_core.get_connection(db_path) as conn:
        res = financial_collector.populate_market_cap(conn, refresh=ctx.get('mc_refresh', False))
    if res.get('skipped'):
        return 'skipped (%s)' % res.get('reason')
    return 'updated=%d rows=%d fetched=%d no_shares=%d' % (
        res['updated'], res['rows'], res.get('fetched', 0), res['no_shares'])


def stage_technical(db_path: Optional[str], ctx: Dict) -> str:
    import technical_analyzer
    calc_date = ctx.get('screen_date') or _latest_trade_date(db_path)
    if not calc_date:
        raise RuntimeError('가격 데이터 없음 — 기술적 분석 불가')
    ctx['screen_date'] = calc_date
    with db_core.get_connection(db_path) as conn:
        counts = technical_analyzer.calculate_all(conn, end_date=calc_date)
    total = sum(counts.values())
    return 'date=%s stocks=%d signals=%d' % (calc_date, len(counts), total)


def stage_news(db_path: Optional[str], ctx: Dict) -> str:
    if not ctx.get('do_news'):
        return 'skipped (do_news=False)'
    import news_crawler
    import sentiment_analyzer
    score_date = ctx.get('screen_date') or _latest_trade_date(db_path)
    if not score_date:
        raise RuntimeError('가격 데이터 없음 — 뉴스 감성 기준일 없음')
    with db_core.get_connection(db_path) as conn:
        news = news_crawler.fetch_all_news(conn, display=ctx.get('news_display', 20))
        if news.get('skipped'):
            return 'skipped (%s)' % news.get('reason')
        sentiment = sentiment_analyzer.aggregate_all(conn, score_date)
    return 'date=%s companies=%d news=%d sentiment=%d errors=%d %s' % (
        score_date, news['companies'], news['rows'], len(sentiment),
        news.get('errors', 0), news.get('error', '')[:80])


def stage_macro(db_path: Optional[str], ctx: Dict) -> str:
    if not ctx.get('do_macro'):
        return 'skipped (do_macro=False)'
    import macro_data
    with db_core.get_connection(db_path) as conn:
        res = macro_data.fetch_macro_data(conn)
        regime = macro_data.detect_market_regime(conn)
    if res.get('skipped'):
        return 'skipped (%s) regime=%s' % (res.get('reason'), regime)
    return 'symbols=%d rows=%d regime=%s' % (res['symbols'], res['rows'], regime)


def stage_simulation(db_path: Optional[str], ctx: Dict) -> str:
    import simulation_runner
    start, end = ctx.get('window') or _price_window(db_path)
    if not start or not end:
        raise RuntimeError('가격 데이터 없음 — 시뮬레이션 불가')
    ctx['window'] = (start, end)
    with db_core.get_connection(db_path) as conn:
        res = simulation_runner.run_batch(conn, start, end, n=ctx.get('n_sim', 9))
    ctx['batch_id'] = res.get('batch_id')
    return 'completed=%d gate_passed=%d batch=%s' % (
        res['completed'], res['gate_passed'], res.get('batch_id', '')[:8])


def stage_fusion(db_path: Optional[str], ctx: Dict) -> str:
    import fusion_analyzer
    import macro_data
    calc_date = ctx.get('screen_date') or _latest_trade_date(db_path)
    if not calc_date:
        raise RuntimeError('가격 데이터 없음 — 융합 분석 불가')
    with db_core.get_connection(db_path) as conn:
        regime = macro_data.detect_market_regime(conn)
        res = fusion_analyzer.calculate_all(conn, calc_date, regime=regime)
    return 'date=%s stocks=%d regime=%s' % (calc_date, len(res), regime)


def stage_optimize(db_path: Optional[str], ctx: Dict) -> str:
    import algo_optimizer
    with db_core.get_connection(db_path) as conn:
        summary = algo_optimizer.apply_optimal_params(conn, batch_id=ctx.get('batch_id'))
    return 'applied=%s best=%s skipped=%d' % (
        summary['applied'], summary['best_strategy'], summary['skipped'])


def stage_report(db_path: Optional[str], ctx: Dict) -> str:
    import reliability_report
    start, end = ctx.get('window') or _price_window(db_path)
    with db_core.get_connection(db_path) as conn:
        report = reliability_report.build_report(
            conn, start, end, batch_id=ctx.get('batch_id'))
    ctx['report'] = report
    return report['text'].replace('\n', ' / ')


STAGES = [
    ('collect', stage_collect),
    ('market_cap', stage_market_cap),
    ('technical', stage_technical),
    ('news', stage_news),
    ('macro', stage_macro),
    ('screening', stage_screening),
    ('fusion', stage_fusion),
    ('simulation', stage_simulation),
    ('optimize', stage_optimize),
    ('report', stage_report),
]


def run_pipeline(db_path: Optional[str] = None, run_date: Optional[str] = None,
                 window: Optional[Tuple[str, str]] = None, do_collect: bool = False,
                 collect_opts: Optional[Dict] = None, do_news: bool = False,
                 news_display: int = 20, do_macro: bool = False, n_sim: int = 9,
                 screen_date: Optional[str] = None, dry_run: bool = False) -> Dict:
    """EOD 파이프라인 실행.

    Returns:
        {run_date, stages: [(name, status)], report}
    """
    db_core.init_db(db_path)
    run_date = run_date or date.today().isoformat()
    ctx = {'do_collect': do_collect, 'collect_opts': collect_opts, 'n_sim': n_sim,
           'window': window, 'screen_date': screen_date,
           'do_news': do_news, 'news_display': news_display,
           'do_macro': do_macro}  # type: Dict
    summary = {'run_date': run_date, 'stages': []}  # type: Dict

    for name, fn in STAGES:
        stage_id = db_ops.log_start(db_path, run_date, name)
        if dry_run:
            db_ops.log_finish(db_path, stage_id, 'skipped', 'dry-run')
            summary['stages'].append((name, 'skipped'))
            continue
        try:
            msg = fn(db_path, ctx)
            db_ops.log_finish(db_path, stage_id, 'completed', msg)
            summary['stages'].append((name, 'completed'))
        except Exception as e:               # 단계 실패 격리 — 다음 단계 계속
            db_ops.log_finish(db_path, stage_id, 'failed', str(e))
            summary['stages'].append((name, 'failed'))

    summary['report'] = ctx.get('report')
    return summary


def _main(argv: Optional[List[str]] = None) -> int:
    import argparse
    p = argparse.ArgumentParser(description='TTAK Quant EOD 파이프라인')
    p.add_argument('--db', default=None, help='DB 경로 (기본 config.DB_PATH)')
    p.add_argument('--collect', action='store_true', help='pykrx/DART 실수집 수행')
    p.add_argument('--dry-run', action='store_true', help='단계 배선만 확인(미실행)')
    p.add_argument('--n-sim', type=int, default=9, help='시뮬레이션 횟수')
    p.add_argument('--news', action='store_true', help='Naver 뉴스 수집 및 감성 집계 수행')
    p.add_argument('--news-display', type=int, default=20, help='종목별 뉴스 조회 건수')
    p.add_argument('--macro', action='store_true', help='yfinance 매크로 데이터 수집 수행')
    p.add_argument('--start', default=None, help='수집 시작 YYYYMMDD (기본 오늘)')
    p.add_argument('--end', default=None, help='수집 종료 YYYYMMDD (기본 오늘)')
    p.add_argument('--years', default=None, help='재무 수집 연도 콤마구분 (예: 2022,2023)')
    p.add_argument('--markets', default=None, help='시장 콤마구분 (예: KOSPI,KOSDAQ)')
    p.add_argument('--stocks', default=None, help='수집 종목코드 콤마구분 (미지정=전체)')
    args = p.parse_args(argv)

    collect_opts = None
    if args.collect:
        collect_opts = {}
        if args.start:
            collect_opts['start'] = args.start
        if args.end:
            collect_opts['end'] = args.end
        if args.years:
            collect_opts['years'] = args.years.split(',')
        if args.markets:
            collect_opts['markets'] = tuple(args.markets.split(','))
        if args.stocks:
            collect_opts['stock_codes'] = args.stocks.split(',')

    summary = run_pipeline(db_path=args.db, do_collect=args.collect,
                           collect_opts=collect_opts, n_sim=args.n_sim,
                           do_news=args.news, news_display=args.news_display,
                           do_macro=args.macro,
                           dry_run=args.dry_run)
    print('[EOD %s]' % summary['run_date'])
    for name, status in summary['stages']:
        print('  %-11s %s' % (name, status))
    if summary.get('report'):
        print('--- 리포트 ---')
        print(summary['report']['text'])
    failed = any(s == 'failed' for _, s in summary['stages'])
    return 1 if failed else 0


if __name__ == '__main__':
    import sys
    sys.exit(_main())
