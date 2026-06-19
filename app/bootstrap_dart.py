"""DART 재무 부트스트랩 — 키 투입 후 1회 실행으로 value/turnaround 실데이터화.

1) DART corp_code 매핑으로 companies의 placeholder corp_code(X+종목코드)를 실제 코드로 교체
2) 지정 종목·연도 재무 수집 (disclosed_at = 실제 공시일 rcept_dt)
3) 스크리닝 재실행 → value/turnaround 결과 출력

사용:
    # app/.env 에 OPENDART_API_KEY 설정 후
    venv/bin/python bootstrap_dart.py [--years 2022,2023,2024] [--screen-date YYYY-MM-DD]
"""
from typing import List, Optional
import argparse

import config
import db_core
import company_master
import financial_collector
import screening


def fix_corp_codes(db_path: Optional[str], api_key: str) -> int:
    """companies의 placeholder corp_code를 DART 실제 corp_code로 교체. 갱신 수 반환."""
    corp_map = company_master.fetch_dart_corp_map(api_key)   # {stock_code: {corp_code,...}}
    updated = 0
    with db_core.get_connection(db_path) as conn:
        for r in conn.execute("SELECT stock_code, corp_code FROM companies").fetchall():
            info = corp_map.get(r['stock_code'])
            if info and info['corp_code'] and info['corp_code'] != r['corp_code']:
                conn.execute("UPDATE companies SET corp_code=? WHERE stock_code=?",
                             (info['corp_code'], r['stock_code']))
                updated += 1
    return updated


def run(db_path: Optional[str], years: List[str], screen_date: Optional[str]) -> None:
    api_key = config.OPENDART_API_KEY
    if not api_key:
        print('OPENDART_API_KEY 없음 — app/.env에 키를 넣으세요. (.env.example 참조)')
        return

    db_core.init_db(db_path)

    n = fix_corp_codes(db_path, api_key)
    print('corp_code 교체:', n)

    with db_core.get_connection(db_path) as conn:
        corp_codes = [r['corp_code'] for r in
                      conn.execute("SELECT corp_code FROM companies").fetchall()]
        # 사업보고서(연간) + 분기 일부까지 수집하면 YoY 비교 가능
        res = financial_collector.collect_financials(
            conn, corp_codes, years, reprt_codes=('11011',))
    print('재무 수집:', res)

    if screen_date is None:
        with db_core.get_connection(db_path) as conn:
            row = conn.execute("SELECT MAX(trade_date) d FROM price_data").fetchone()
            screen_date = row['d']

    with db_core.get_connection(db_path) as conn:
        counts = screening.run_all_screens(conn, screen_date)
        print('스크리닝(%s): %s' % (screen_date, counts))
        for strat in ('value', 'turnaround'):
            rows = conn.execute(
                "SELECT stock_code, score, signals FROM screening_results "
                "WHERE strategy=? AND screen_date=? ORDER BY score DESC LIMIT 5",
                (strat, screen_date)).fetchall()
            print('  [%s]' % strat)
            for r in rows:
                print('    %s  score=%.0f  %s' % (r['stock_code'], r['score'], r['signals']))


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description='DART 재무 부트스트랩')
    p.add_argument('--db', default=None)
    p.add_argument('--years', default='2022,2023,2024')
    p.add_argument('--screen-date', default=None)
    args = p.parse_args(argv)
    run(args.db, args.years.split(','), args.screen_date)
    return 0


if __name__ == '__main__':
    import sys
    sys.exit(main())
